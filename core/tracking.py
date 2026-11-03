"""완료 추적기 — 환불·분쟁은 "접수"가 아니라 "입금 확인"까지가 완료 (TC-STR-006).

케이스가 접수/합의되면 tracking 상태로 전환되고, 이 모듈이:
  ① 상대방의 완료 통보(입금·환불 완료 메일)를 확인 증빙으로 기록하고
  ② 기한(expected_by)이 지나면 상대방에게 넛지 메일을 보내고 (최대 2회)
  ③ 넛지로도 안 되면 에스컬레이션 경로(소비자원 등)를 고객에게 제안한다.

확정 전에는 Flow가 절대 "완료"로 전환되지 않는다 (허위 완료 방지, TC-DEL-010).

공개 인터페이스:
  schedule(case) -> None              # 추적 시작 (기한 = 플레이북 tracking_days)
  mark_confirmed(case, summary, evidence_path="") -> None
  run_tick() -> dict                  # 추적 1틱: 확정 → 완결 / 기한 초과 → 넛지
"""
from __future__ import annotations

from datetime import timedelta

from . import agents, cases, common, flow, notify

MAX_NUDGES = 2

# 상대방 메일에서 "환불 확정"을 인식하는 신호
CONFIRM_SIGNALS = ("환불 완료", "환불이 완료", "입금 완료", "입금되었", "환급 완료",
                   "처리 완료", "refund completed", "환불 처리되었")


def schedule(case: dict) -> None:
    """추적 시작 — 기한 설정 + 고객에게 '입금까지 지켜본다' 안내."""
    pb = cases.playbook_of(case)
    days = pb.get("tracking_days", 7)
    case["tracking"]["expected_by"] = common.iso(common.now() + timedelta(days=days))
    cases.set_status(case, "tracking")
    tracker = agents.assign("tracker")
    flow.add_step(case["flow"], agents.tag(tracker),
                  f"완료 추적 시작 — {days}일 안에 실제 입금(처리 완료)을 확인할 때까지 "
                  f"이 건은 끝난 게 아니에요. 기한: {case['tracking']['expected_by'][:10]}")


def is_confirmation(text: str) -> bool:
    low = (text or "").lower()
    return any(s.lower() in low for s in CONFIRM_SIGNALS)


def mark_confirmed(case: dict, summary: str, evidence_path: str = "") -> None:
    """상대방 완료 통보 수신 — 확인 증빙 기록. 완결은 run_tick이 수행."""
    import shutil
    from pathlib import Path
    case["tracking"]["confirmed"] = True
    case["tracking"]["confirm_summary"] = common.mask_sensitive(summary)[:200]
    if evidence_path and Path(evidence_path).exists():
        # 원본 메일은 이후 보관함으로 이동되므로 증빙 사본을 남긴다
        dest_dir = common.EVIDENCE / case["id"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"confirm-{Path(evidence_path).name}"
        shutil.copy2(evidence_path, dest)
        cases.add_evidence(case, str(dest), "완료 확인 근거(상대방 통보)")
    cases.save(case)


def _resolve(case: dict) -> None:
    """확정된 케이스 완결 — 증빙과 함께 Flow 완료 (여기서만 complete 호출)."""
    cases.set_status(case, "resolved")
    amount = case["intent"].get("amount")
    amount_txt = f" {amount:,}원" if amount else ""
    evid = ", ".join(e["path"] for e in case["evidence"][-3:]) or "케이스 라운드 기록"
    reclaimed = float(case.get("est_hours") or 2.0)
    flow.complete(case["flow"],
                  f"환불{amount_txt} 실제 처리 확인 — {case['tracking'].get('confirm_summary', '상대방 완료 통보')} "
                  f"/ 증빙: {evid}",
                  reclaimed_hours=reclaimed)
    # 큐에 남아 있던 케이스 아이템 정리 (슬롯은 이미 반납되었을 수 있음)
    for state in ("active", "pending"):
        for it in common.list_queue(state):
            if it.get("case") == case["id"]:
                it["charged"] = True
                common.move_queue_item(it, state, "done")


def _nudge(case: dict) -> None:
    """기한 초과 — 상대방에게 처리 확인 요청 메일 (최대 MAX_NUDGES회)."""
    merchant = case["intent"].get("merchant_email")
    pb = cases.playbook_of(case)
    n = case["tracking"]["nudges"] + 1
    case["tracking"]["nudges"] = n
    case["tracking"]["expected_by"] = common.iso(common.now() + timedelta(days=3))
    cases.save(case)
    if merchant:
        amount = case["intent"].get("amount")
        path = common.write_outbox({
            "to": merchant,
            "subject": f"[처리 확인 요청 {n}차] {case['intent'].get('merchant', '')} "
                       f"환불 건 (케이스 {case['id']})",
            "thread": case["flow"],
            "body": "\n".join([
                "안녕하세요, 고객을 대리해 진행 중인 환불 건의 처리 현황 확인을 요청드립니다.",
                f"- 주문/계약번호: {case['intent'].get('order_no', '별첨')}",
                f"- 금액: {amount:,}원" if amount else "- 금액: 별첨",
                f"- 접수/합의 시점: {case['rounds'][0]['ts'][:10] if case['rounds'] else case['created'][:10]}",
                "",
                "합의(접수)된 환불이 아직 입금 확인되지 않았습니다. 처리 예정일을 회신 부탁드립니다.",
                f"기한 내 처리가 어려우면 {pb.get('escalation', '분쟁조정 절차')}로 진행하겠습니다.",
            ]),
        })
        cases.add_round(case, "out", f"{n}차 처리 확인 넛지 발송", str(path))
    tracker = agents.assign("tracker")
    flow.add_step(case["flow"], agents.tag(tracker),
                  f"기한 초과 — 상대방에게 {n}차 처리 확인 요청 발송 (최대 {MAX_NUDGES}회)")


def _escalate(case: dict) -> None:
    """넛지 한도 초과 — 에스컬레이션 경로를 고객에게 제안 (임의 진행 금지)."""
    pb = cases.playbook_of(case)
    cases.set_status(case, "awaiting_customer")
    flow.ask_customer(case["flow"],
                      f"상대방이 {MAX_NUDGES}회 확인 요청에도 처리를 완료하지 않았어요. "
                      f"다음 단계로 {pb.get('escalation', '분쟁조정 신청')}을 추천해요. "
                      "진행을 원하시면 \"에스컬레이션\", 더 기다리시려면 \"대기\", "
                      "중단하시려면 \"취소\"라고 회신해 주세요.")


def portal_recheck(case: dict) -> bool:
    """포털형 케이스의 처리 상태 재확인 — egolite 세션으로 결과 페이지 확인.

    확인되면 mark_confirmed. 봇 차단 포털은 재확인하지 않는다(False).
    """
    from . import egolite
    if case["channel"] not in ("portal", "hybrid"):
        return False
    r = egolite.run_intent(case, "환불/해지 처리 상태 확인",
                           case["intent"].get("portal_url", ""))
    if r.get("ok") and r.get("confirmation_no"):
        mark_confirmed(case, f"포털 재확인 — 처리 완료 ({r['confirmation_no']})",
                       (r.get("evidence") or [""])[0])
        return True
    return False


def run_tick() -> dict:
    """추적 1틱 — 서비스 사이클·`python3 -m core track-run`에서 호출."""
    stats = {"resolved": 0, "nudged": 0, "escalated": 0, "watching": 0}
    now_iso = common.iso()
    for case in cases.list_cases("tracking"):
        if not case["tracking"].get("confirmed"):
            portal_recheck(case)
        if case["tracking"].get("confirmed"):
            _resolve(case)
            stats["resolved"] += 1
            continue
        expected = case["tracking"].get("expected_by") or now_iso
        if expected < now_iso:
            if case["tracking"]["nudges"] >= MAX_NUDGES:
                _escalate(case)
                stats["escalated"] += 1
            else:
                _nudge(case)
                stats["nudged"] += 1
        else:
            stats["watching"] += 1
    return stats
