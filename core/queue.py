"""티어 슬롯 기반 파일 큐 — TC-OPS-003/004/006/007, TC-DEL-005.

상태 디렉토리: data/queue/pending|active|done|cancelled (common.py 계약).
- 고객 티어별 동시 슬롯(common.TIER_SLOTS) 안에서 pending→active FIFO 승격
- active 실행은 v0 시뮬레이션: 결제 승인 게이트(approval.gate) 4분기
- 대기 타임아웃: deadline 경과 pending에 지연 통지 1회 (아이템 유지)
- 사용량: done 이동 시 data/usage/<customer>.json 월별 est_hours 누적,
  티어 한도 80% 도달 시 사전 통지 1회 (TC-OPS-006)
"""
from __future__ import annotations

import re

from . import approval, common, executor, flow, notify

# 월 위임 시간 한도 (ops/pricing.md: One ~10h / Flow ~40h / Life 무제한급)
TIER_HOURS = {"one": 10.0, "flow": 40.0, "life": 999.0}
USAGE_DIR = common.DATA / "usage"


# ── enqueue ──────────────────────────────────────────────

def enqueue(customer_id: str, kind: str, summary: str, flow_id: str,
            amount: int = 0, est_hours: float = 0.0,
            priority: str = "normal", case_id: str = "", body: str = "") -> str:
    """pending에 아이템 생성. 슬롯이 없어 대기면 대기 순번·예상을 1회 안내.

    priority="high"는 스트레스 유형(환불·분쟁 등) — 먼저 대응해 멘탈 케어에
    기여한다 (TC-STR-001). case_id는 케이스 연동, body는 실행기 참고용 원문.
    """
    from . import agents
    common.ensure_dirs()
    created = common.now()
    item_id = f"{created.strftime('%Y%m%d-%H%M%S-%f')}-{customer_id}-{common.slug(summary, 24)}"
    role = "negotiator" if kind.startswith("case:") else "resolver"
    item = {
        "id": item_id,
        "customer": customer_id,
        "created": created.isoformat(),  # 마이크로초 포함 → 같은 초에도 FIFO 보장
        "kind": kind,
        "summary": summary,
        "flow": flow_id,
        "amount": amount,
        "est_hours": est_hours,
        "priority": priority,
        "case": case_id,
        "body": common.mask_sensitive(body)[:500],
        "assignee": agents.assign(role)["id"],
        "approved": None,
        "asked": False,              # 승인 질문 1회 플래그 (재질문 금지)
        "notified_hold": False,      # 승인 무응답 보류 통지 1회 플래그
        "notified_timeout": False,   # 대기 타임아웃 통지 1회 플래그
        "charged": None,             # done=True / cancelled=False (미차감)
        "deadline": common.default_deadline(),
    }
    common.write_json(common.queue_item_path("pending", item_id), item)
    _maybe_send_wait_notice(item)
    return item_id


def _maybe_send_wait_notice(item: dict) -> None:
    prof = common.load_profiles().get(item["customer"])
    if not prof:
        return
    slots = common.TIER_SLOTS.get(prof.get("tier", "one"), 1)
    active_cnt = sum(1 for i in common.list_queue("active")
                     if i["customer"] == item["customer"])
    ahead_pending = sum(1 for i in common.list_queue("pending")
                        if i["customer"] == item["customer"]
                        and i["created"] < item["created"])
    ahead = active_cnt + ahead_pending
    if ahead < slots:
        return  # 바로 다음 틱에 착수 가능 → 대기 안내 불필요
    rank = ahead - slots + 1
    lines = [
        f"\"{item['summary']}\" 요청을 접수했어요.",
        f"지금 진행 중인 일이 있어 대기열에 올려두었어요. 대기 순번: {rank}번째.",
        f"늦어도 {item['deadline']} 전에는 시작될 예정이고, 슬롯이 비는 대로 바로 착수해 이 스레드로 알려드릴게요.",
    ]
    if prof.get("tier") == "one":
        # 상위 티어 안내는 강요 없이 딱 1문장 1회 (TC-OPS-003)
        lines.append("참고로, Unplug Flow 티어에서는 동시에 2건까지 대기 없이 진행돼요 — 원하실 때만 살펴보세요.")
    notify.send(item["customer"],
                f"대기 안내: {item['summary']} (대기 {rank}번째)",
                "\n".join(lines), thread=item["flow"])


# ── 한 틱 처리 ────────────────────────────────────────────

def run_tick() -> dict:
    """한 번의 틱: 슬롯 승격 → active 실행 → 대기 타임아웃 점검."""
    common.ensure_dirs()
    profiles = common.load_profiles()
    stats = {"promoted": 0, "executed": 0, "waiting": 0, "timeouts": 0}

    # 1. 고객별 티어 슬롯 내 pending→active 승격
    #    스트레스 유형(priority=high)이 먼저, 같은 우선순위끼리는 FIFO (TC-STR-001)
    active_cnt: dict[str, int] = {}
    for it in common.list_queue("active"):
        active_cnt[it["customer"]] = active_cnt.get(it["customer"], 0) + 1
    pending_sorted = sorted(
        common.list_queue("pending"),
        key=lambda i: (0 if i.get("priority") == "high" else 1, i["created"]))
    for it in pending_sorted:
        prof = profiles.get(it["customer"], {})
        slots = common.TIER_SLOTS.get(prof.get("tier", "one"), 1)
        if active_cnt.get(it["customer"], 0) < slots:
            common.move_queue_item(it, "pending", "active")
            active_cnt[it["customer"]] = active_cnt.get(it["customer"], 0) + 1
            stats["promoted"] += 1

    # 2. active 실행 (v0 시뮬레이션)
    for it in common.list_queue("active"):
        _execute(it, profiles.get(it["customer"], {}), stats)

    # 3. 대기 타임아웃: deadline 지난 pending → 지연 통지 1회, 아이템 유지
    now_iso = common.iso()
    for it in common.list_queue("pending"):
        stats["waiting"] += 1
        if it["deadline"] < now_iso and not it.get("notified_timeout"):
            new_eta = common.default_deadline()
            notify.send(
                it["customer"],
                f"대기 지연 안내: {it['summary']}",
                "\n".join([
                    f"\"{it['summary']}\" 요청이 예상보다 오래 대기하고 있어요. 죄송해요.",
                    "지연 사유: 앞선 위임 건의 처리가 예상보다 길어지고 있어요.",
                    f"새 예상 시작 시점: 늦어도 {new_eta} 전.",
                    "계속 대기하시려면 회신 없이 그대로 두시면 되고, 취소를 원하시면 이 메일에 \"취소\"라고 회신해 주세요.",
                    "취소하셔도 위임 시간(사용량)은 전혀 차감되지 않아요.",
                ]),
                thread=it["flow"])
            it["notified_timeout"] = True
            common.write_json(common.queue_item_path("pending", it["id"]), it)
            stats["timeouts"] += 1
    return stats


def _execute(it: dict, prof: dict, stats: dict) -> None:
    fid = it["flow"]
    if it.get("hold"):
        # 보안 이벤트·사람 개입·고객 확인 대기 중 — 재처리하지 않음
        stats["waiting"] += 1
        return
    if (it.get("kind") or "").startswith("case:"):
        _launch_case(it, prof, stats)
        return
    if it.get("approved") is True:
        # 고객이 명시적으로 승인 → 결제 진행 후 실행 (게이트 기록은 그대로 유지)
        flow.add_step(fid, "it",
                      f"고객 승인 확인 — 결제 진행: {it['summary']} / {it['amount']}원")
        _execute_via_executor(it, prof, stats)
        return
    if it.get("approved") is False:
        # 고객 거부 → 결제 없이 안전 종결, 사용량 미차감
        it["charged"] = False
        common.move_queue_item(it, "active", "cancelled")
        flow.cancel(fid, "고객이 결제 승인을 거부하셔서 결제 없이 안전하게 종결했어요. (사용량 미차감)")
        stats["executed"] += 1
        return
    if it["amount"] > 0:
        verdict = approval.gate(prof, it["amount"], it)
        if verdict == "proceed":
            flow.add_step(fid, "it",
                          f"결제 직전 내역 요약: {it['summary']} / {it['amount']}원 (한도 이내 자동 진행)")
            _finish(it, prof, f"결제 완료: {it['summary']} / {it['amount']}원 (한도 이내 자동 진행)")
            stats["executed"] += 1
            return
        # need_approval
        if not it.get("asked"):
            flow.ask_customer(fid, (
                f"결제 승인이 필요해요. 금액: {it['amount']}원 "
                f"(사전 승인 한도 {prof.get('approval_limit', 0)}원 초과) / "
                f"내용: {it['summary']} / "
                "승인 방법: 이 메일에 \"승인\" 또는 \"거부\"라고 회신해 주세요."))
            it["asked"] = True  # 재질문 금지
            common.write_json(common.queue_item_path("active", it["id"]), it)
        elif it["deadline"] < common.iso() and not it.get("notified_hold"):
            # 승인 무응답 타임아웃 → 결제하지 않고 보류 통지 1회, 아이템 유지
            flow.add_step(fid, "it", (
                f"승인 응답 대기 타임아웃 — 결제하지 않고 보류 중이에요: "
                f"{it['summary']} / {it['amount']}원. \"승인\" 회신 주시면 바로 재개할게요."))
            it["notified_hold"] = True
            common.write_json(common.queue_item_path("active", it["id"]), it)
            stats["timeouts"] += 1
        stats["waiting"] += 1
        return
    # amount == 0 → 바로 실행·완료 (실행기 경유)
    _execute_via_executor(it, prof, stats)


def _launch_case(it: dict, prof: dict, stats: dict) -> None:
    """케이스 아이템 착수 — 이메일 협상 개시 또는 포털 수행 (TC-STR-003/004/005).

    케이스는 결과 확인(입금 등)까지가 완료이므로, 여기서는 착수까지만 하고
    슬롯을 반납(done)한다. Flow 완결은 tracking이 확정 후에만 수행한다.
    """
    from . import cases as cases_mod, egolite, hitl, negotiation, tracking
    fid = it["flow"]
    case = cases_mod.load(it.get("case", ""))
    if case is None:
        flow.ask_customer(fid, f"케이스 기록({it.get('case')})을 찾지 못해 보류 중이에요. 다시 요청해 주세요.")
        it["hold"] = "case_missing"
        common.write_json(common.queue_item_path("active", it["id"]), it)
        stats["waiting"] += 1
        return
    if case["status"] != "open":
        # 이미 착수된 케이스 — 슬롯만 반납
        _release_case_slot(it, prof, stats)
        return

    if case["channel"] == "email":
        negotiation.start(case)
        _release_case_slot(it, prof, stats,
                           note=f"협상 개시 완료 — 상대방 회신 대기 (케이스 {case['id']})")
        return

    # portal / hybrid — egolite 세션으로 절차 수행
    intent_text = f"{cases_mod.playbook_of(case)['opener']} — {it['summary']}"
    r = egolite.run_intent(case, intent_text, case["intent"].get("portal_url", ""))
    if r.get("injection"):
        _security_hold(it, fid, r, stats)
        return
    if r.get("blocked"):
        portal = egolite._match_portal(case["intent"].get("portal_url", ""),
                                       case["intent"].get("merchant", ""))
        steps = (portal or {}).get("manual_steps") or [
            "해당 포털에 접속해 환불/해지 절차 진행", "접수번호를 완료 보고에 입력"]
        kind = "takeover" if any("takeover" in s.lower() or "본인" in s or "고객" in s
                                 for s in steps) else "manual"
        hitl.request(case, r["summary"], steps, kind=kind)
        _release_case_slot(it, prof, stats,
                           note=f"봇 차단 포털 — 사람 개입 가이드 발행 (케이스 {case['id']})")
        return
    if not r.get("ok"):
        cases_mod.add_round(case, "sys", f"포털 수행 실패: {r['summary']}")
        it["fail_count"] = int(it.get("fail_count", 0)) + 1
        flow.add_step(fid, "it", f"실행 실패({it['fail_count']}회) — 안전하게 중단: {r['summary']}")
        if it["fail_count"] >= 2:
            flow.ask_customer(fid, (
                f"\"{it['summary']}\" 포털 수행이 반복 실패해 보류 중이에요. "
                "대안: ① 재시도 ② 사람이 직접 처리 ③ 취소 — 번호로 회신해 주세요."))
            it["hold"] = "await_customer"
        common.write_json(common.queue_item_path("active", it["id"]), it)
        stats["waiting"] += 1
        return
    for e in r.get("evidence", []):
        cases_mod.add_evidence(case, e, "포털 접수 증빙")
    cases_mod.add_round(case, "sys", f"포털 접수 완료: {r['summary']}")
    flow.add_step(fid, "it", f"포털 접수 완료: {r['summary']} / {executor.evidence_note(r)}")
    tracking.schedule(case)
    _release_case_slot(it, prof, stats,
                       note=f"포털 접수 완료 — 실제 처리(입금) 확인까지 추적 (케이스 {case['id']})")


def _release_case_slot(it: dict, prof: dict, stats: dict, note: str = "") -> None:
    """케이스 착수 후 슬롯 반납 — Flow는 완결하지 않는다 (추적이 완결 담당)."""
    it["charged"] = True
    common.move_queue_item(it, "active", "done")
    if note:
        flow.add_step(it["flow"], "concierge", note, notify_customer=False)
    _charge_usage(it["customer"], float(it.get("est_hours") or 2.0), prof)
    stats["executed"] += 1


def _security_hold(it: dict, fid: str, result: dict, stats: dict) -> None:
    """인젝션 감지 — 수행 중단 + 보안 이벤트 기록 + 고객 안내 (TC-DEL-011)."""
    flow.add_step(fid, "it", f"[보안 이벤트] {result['summary']} — 페이지 지시는 따르지 않았어요")
    flow.ask_customer(fid, (
        f"\"{it['summary']}\" 수행 중 방문한 페이지에서 악성 지시가 감지되어 "
        "안전하게 중단했어요. 다른 경로로 재시도할까요? (재시도/취소로 회신)"))
    it["hold"] = "security"
    common.write_json(common.queue_item_path("active", it["id"]), it)
    stats["waiting"] += 1


def _execute_via_executor(it: dict, prof: dict, stats: dict) -> None:
    """게이트 통과 후의 실제 수행 — executor 경유 (TC-DEL-010 지향).

    성공: 실행 요약 step(+증빙 노트) → done 이동 → flow 완결.
    단, 외부 거래 수행(browser 계열)은 증빙 없이는 완료 처리하지 않는다.
    실패: 사유 step 기록, active 유지 + fail_count 증가,
          2회 이상이면 "확인 필요" 전환·대안 안내 (TC-DEL-004).
    봇 차단: 재시도 없이 즉시 사람 개입 가이드 발행 (TC-DEL-004 ⑤).
    """
    from . import hitl
    fid = it["flow"]
    result = executor.run(it, prof)
    note = executor.evidence_note(result)

    if result.get("injection"):
        _security_hold(it, fid, result, stats)
        return

    if result.get("blocked"):
        hitl.request_for_item(it, result["summary"], [
            "차단된 포털에 직원 계정/브라우저로 직접 접속",
            f"요청 내용 수행: {it['summary']}",
            "완료 화면의 접수·확정 번호를 완료 보고에 입력"])
        it["hold"] = "handoff"
        common.write_json(common.queue_item_path("active", it["id"]), it)
        stats["waiting"] += 1
        return

    if result.get("ask"):
        # 선택지 발생 — 대안을 한 번에 묶어 1회만 질문 (TC-DEL-002)
        if not it.get("asked_alt"):
            alts = result.get("alternatives", [])
            opts = " / ".join(f"{i}. {a}" for i, a in enumerate(alts, 1))
            flow.ask_customer(fid, (
                f"\"{it['summary']}\" 진행 중 희망 조건이 마감되었어요. "
                f"대안을 한 번에 정리했어요 — {opts} — 원하시는 번호로 회신해 주세요. "
                "(추가 질문 없이 이 한 번으로 끝낼게요)"))
            it["asked_alt"] = True
            it["partial"] = result.get("partial", [])
            it["hold"] = "await_choice"
            common.write_json(common.queue_item_path("active", it["id"]), it)
        stats["waiting"] += 1
        return

    if result["ok"]:
        if executor.requires_evidence(it) and not result.get("evidence"):
            # 증빙 없는 완료 주장 — 완결 차단 (TC-DEL-010)
            flow.add_step(fid, "it",
                          f"완료 보고에 증빙이 없어 완결을 보류했어요: {result['summary']} "
                          "(주문번호·영수증·스크린샷 중 1개 이상 필요)")
            it["hold"] = "no_evidence"
            common.write_json(common.queue_item_path("active", it["id"]), it)
            stats["waiting"] += 1
            return
        flow.add_step(fid, "it", f"실행 요약: {result['summary']} / {note}")
        _finish(it, prof, result["summary"], reclaimed=result.get("reclaimed"))
        stats["executed"] += 1
        return

    it["fail_count"] = int(it.get("fail_count", 0)) + 1
    flow.add_step(fid, "it",
                  f"실행 실패({it['fail_count']}회) — 안전하게 중단: {result['summary']} / {note}")
    if it["fail_count"] >= 2:
        partial = it.get("partial") or result.get("partial")
        partial_txt = f" 지금까지의 중간 결과: {partial}" if partial else ""
        flow.ask_customer(fid, (
            f"\"{it['summary']}\" 수행이 반복 실패해 결제·실행 없이 보류 중이에요. "
            f"사유: {result['summary']} /{partial_txt} "
            "대안: ① 다른 사이트·시간대로 재시도 ② 조건을 바꿔 다시 위임 ③ 취소. "
            "원하시는 번호(또는 \"취소\")로 이 메일에 회신해 주세요."))
        it["hold"] = "await_customer"
    common.write_json(common.queue_item_path("active", it["id"]), it)
    stats["waiting"] += 1


def _finish(it: dict, prof: dict, summary: str, reclaimed: float | None = None) -> None:
    """done 이동 + flow 완결 + 사용량 차감 (reclaimed 미지정 시 기존 est_hours 로직)."""
    it["charged"] = True
    common.move_queue_item(it, "active", "done")
    est = float(reclaimed if reclaimed is not None else (it.get("est_hours") or 0.0))
    flow.complete(it["flow"], summary, reclaimed_hours=est if est > 0 else None)
    _charge_usage(it["customer"], est, prof)
    if est > 0:
        # 확보된 시간 → 오프라인 경험 추천 (TC-OFF-001). 실패해도 완결은 유지.
        try:
            from . import recommend
            recommend.maybe_recommend(it["flow"], it["customer"], est)
        except Exception:
            pass


def resume_choice(item_id: str, choice_text: str) -> dict | None:
    """고객이 대안 번호를 회신 — hold 해제 + 선택 반영, 다음 틱에 재실행 (TC-DEL-002)."""
    for state in ("active", "pending"):
        p = common.queue_item_path(state, item_id)
        if p.exists():
            it = common.read_json(p)
            alts = it.get("partial") or []
            m = re.match(r"\s*(\d)", choice_text or "")
            idx = int(m.group(1)) - 1 if m else 0
            chosen = alts[idx] if (alts and isinstance(alts[0], str)
                                   and 0 <= idx < len(alts)) else (choice_text or "").strip()
            it["alt_choice"] = chosen
            it.pop("hold", None)
            common.write_json(p, it)
            flow.add_step(it["flow"], "concierge", f"고객 선택 수신: \"{chosen}\" — 재개합니다")
            return it
    return None


def finish_after_hitl(item_id: str, note: str, confirmation_no: str = "") -> dict | None:
    """사람 처리 완료 보고로 보류 아이템 완결 — 사람 증빙 첨부 (TC-DEL-004 ⑤)."""
    p = common.queue_item_path("active", item_id)
    if not p.exists():
        return None
    it = common.read_json(p)
    receipt = common.EVIDENCE / it["id"] / f"manual-{common.ts()}.json"
    common.write_json(receipt, {"mode": "human", "note": common.mask_sensitive(note),
                                "confirmation_no": confirmation_no, "ts": common.iso()})
    flow.add_step(it["flow"], "it/haru",
                  f"사람 처리 완료 보고: {common.mask_sensitive(note)}"
                  + (f" (접수번호 {confirmation_no})" if confirmation_no else "")
                  + f" / 증빙: {receipt}")
    it.pop("hold", None)
    prof = common.load_profiles().get(it["customer"], {})
    _finish(it, prof, f"{it['summary']} — 사람 개입으로 처리 완료"
            + (f" (접수번호 {confirmation_no})" if confirmation_no else ""))
    return it


# ── 취소 / 승인·거부 ──────────────────────────────────────

def cancel(item_id: str, by_customer: bool = True) -> dict | None:
    """pending/active 어디서든 cancelled로 이동. 사용량 미차감(charged=False).

    진행 중이던 중간 결과(partial)가 있으면 고객에게 함께 반환한다 (TC-DEL-009).
    """
    for state in ("pending", "active"):
        p = common.queue_item_path(state, item_id)
        if p.exists():
            it = common.read_json(p)
            it["charged"] = False  # 미차감 기록
            common.move_queue_item(it, state, "cancelled")
            who = "고객 요청으로" if by_customer else "운영 판단으로"
            msg = f"{who} 취소했어요. 위임 시간(사용량)은 차감되지 않아요."
            partial = it.get("partial")
            if partial:
                if isinstance(partial, list) and partial and isinstance(partial[0], dict):
                    mid = " / ".join(f"{c.get('rank', '')} {c.get('name', '')} {c.get('price', '')}"
                                     for c in partial[:3])
                else:
                    mid = " / ".join(str(x) for x in list(partial)[:3])
                msg += f" 지금까지의 중간 결과를 남겨드려요: {mid}"
            flow.cancel(it["flow"], msg)
            return it
    return None


def _set_approved(item_id: str, value: bool) -> dict | None:
    for state in ("active", "pending"):
        p = common.queue_item_path(state, item_id)
        if p.exists():
            it = common.read_json(p)
            it["approved"] = value
            common.write_json(p, it)
            return it
    return None


def approve(item_id: str) -> dict | None:
    """고객 승인 기록 — 다음 tick에서 결제 진행 후 done."""
    return _set_approved(item_id, True)


def reject(item_id: str) -> dict | None:
    """고객 거부 기록 — 다음 tick에서 결제 없이 cancelled."""
    return _set_approved(item_id, False)


# ── 사용량 (월별 est_hours 누적, 80% 사전 통지) ───────────

def usage_path(customer_id: str):
    return USAGE_DIR / f"{customer_id}.json"


def _charge_usage(customer_id: str, hours: float, prof: dict) -> None:
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    p = usage_path(customer_id)
    data = common.read_json(p) if p.exists() else {"monthly": {}, "notified_months": []}
    month = common.now().strftime("%Y-%m")
    used = round(data["monthly"].get(month, 0.0) + hours, 3)
    data["monthly"][month] = used
    limit = TIER_HOURS.get(prof.get("tier", "one"), 10.0)
    if used >= 0.8 * limit and month not in data["notified_months"]:
        remaining = max(round(limit - used, 1), 0)
        notify.send(customer_id, "이번 달 위임 시간 한도 80% 도달 안내", "\n".join([
            f"이번 달 위임 시간이 티어 한도의 80%에 도달했어요. (사용 {used}h / 한도 {limit}h, 잔여 약 {remaining}h)",
            "한도를 넘길 것 같으면 두 가지 중 고르실 수 있어요:",
            "1) 다음 달 초기화까지 신규 위임을 대기열에 두기",
            "2) 상위 티어로 업그레이드해 한도를 늘리기",
            "참고: 위임 수행 시간만 차감되고, 문진·명확화 대화는 차감되지 않아요.",
        ]))
        data["notified_months"].append(month)
    common.write_json(p, data)
