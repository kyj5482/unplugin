"""이메일 협상 엔진 — 상대방과 메일을 주고받아 결과를 내는 케이스 (TC-STR-003).

환불 분쟁처럼 "과거 히스토리를 기반으로 상대 이메일과 지속적으로 주고받으며
결과를 내야 하는" 업무를 멀티라운드 상태기계로 수행한다.

라운드 사다리 (상대가 거부할수록 단계적으로 강해진다):
  1R 정중한 요구 + 근거(플레이북 opener) + 회신 기한
  2R 근거 재제시 + 법적 기준 명시 + 처리 기한 통보
  3R+ 최후 통첩 + 에스컬레이션(소비자원 등) 예고
  max_rounds 초과 → 임의 진행하지 않고 고객에게 에스컬레이션 선택지 제시

상대 회신 분기:
  수락("환불 처리/접수") → 완료 추적으로 전환 (tracking.schedule)
  부분 제안("50%만")   → 요구액의 90% 이상이면 수락, 미만이면 고객에게 1회 질문
  거부("규정상 불가")   → 다음 라운드 발송
  무응답/모호          → 리마인더

공개 인터페이스:
  start(case) -> None
  handle_reply(case, mail) -> str   # 처리 결과 action 문자열
"""
from __future__ import annotations

import re

from . import agents, cases, common, flow, tracking

ACCEPT_SIGNALS = ("환불 처리", "환불해 드리", "환불해드리", "접수되었", "처리하겠",
                  "승인되었", "환불 진행", "환급 진행", "반환하겠")
REJECT_SIGNALS = ("불가", "어렵습니다", "어려워", "규정상", "거절", "해당되지 않",
                  "환불이 안", "약관에 따라 불가")
_PARTIAL_PCT = re.compile(r"(\d{1,3})\s*%")
_PARTIAL_WON = re.compile(r"([\d,]{4,})\s*원")

REPLY_DEADLINE_DAYS = 3


def _negotiator(case: dict) -> dict:
    ag = agents.assign("negotiator")
    case.setdefault("assignee", ag["id"])
    return ag


def _history_block(case: dict) -> str:
    """지금까지의 주고받은 기록 요약 — 매 라운드 메일에 포함해 맥락을 유지."""
    if not case["rounds"]:
        return ""
    lines = ["", "— 지금까지의 경과 —"]
    for r in case["rounds"][-6:]:
        who = {"out": "당사", "in": "귀사", "sys": "시스템"}.get(r["direction"], r["direction"])
        lines.append(f"  · {r['ts'][:10]} [{who}] {r['summary'][:80]}")
    return "\n".join(lines)


def _send_round(case: dict, stage: int, extra: str = "") -> None:
    """라운드 사다리에 따라 상대방에게 메일 발송 + 라운드 기록."""
    pb = cases.playbook_of(case)
    intent = case["intent"]
    merchant = intent.get("merchant_email", "")
    amount = intent.get("amount")
    amount_txt = f"{amount:,}원" if amount else "결제 금액 전액"

    if stage <= 1:
        tone = [f"안녕하세요. 고객 위임을 받아 아래 건의 환불을 정식으로 요청드립니다.",
                f"근거: {pb['opener']}",
                f"요청: {amount_txt} 환불, {REPLY_DEADLINE_DAYS}일 내 회신 부탁드립니다."]
        label = "1차 정중한 요구"
    elif stage == 2:
        tone = ["앞서 요청드린 환불 건에 대해 다시 연락드립니다.",
                f"근거를 재차 말씀드립니다: {pb['opener']}.",
                f"법정 기준에 따라 {amount_txt}의 반환 의무가 있으며, "
                f"{REPLY_DEADLINE_DAYS}일 내 처리 계획 회신을 요청드립니다."]
        label = "2차 근거 재제시·기한 통보"
    else:
        tone = ["수차례 요청에도 처리가 이뤄지지 않아 최종 통지드립니다.",
                f"본 건이 해결되지 않으면 {pb.get('escalation', '분쟁조정 절차')}를 진행할 예정입니다.",
                f"최종 기한: {REPLY_DEADLINE_DAYS}일. {amount_txt} 환불을 다시 요구합니다."]
        label = f"{stage}차 최후 통첩·에스컬레이션 예고"
    if extra:
        tone.append(extra)

    body = "\n".join([
        *tone,
        f"- 주문/계약번호: {intent.get('order_no', '별첨')}",
        f"- 대상: {intent.get('merchant', '귀사')} / 고객 요청 요지: {case['request'][:120]}",
        _history_block(case),
        "",
        "본 메일은 고객의 위임을 받은 Unplugin 컨시어지가 발송했습니다.",
    ])
    path = common.write_outbox({"to": merchant, "thread": case["flow"],
                                "subject": f"[환불 요청 {stage}차] {intent.get('merchant', '')} "
                                           f"{amount_txt} (케이스 {case['id']})",
                                "body": body})
    cases.add_round(case, "out", label, str(path))
    ag = _negotiator(case)
    flow.add_step(case["flow"], agents.tag(ag),
                  f"상대방에게 {label} 발송 → {merchant} (회신 기한 {REPLY_DEADLINE_DAYS}일)")


def _round_count(case: dict) -> int:
    return sum(1 for r in case["rounds"] if r["direction"] == "out")


def start(case: dict) -> None:
    """협상 개시 — 1차 요구 발송."""
    cases.set_status(case, "negotiating")
    _send_round(case, 1)


def _agree(case: dict, mail: dict, note: str) -> str:
    cases.add_round(case, "in", f"상대방 수락: {note[:100]}", mail.get("path", ""))
    ag = _negotiator(case)
    flow.add_step(case["flow"], agents.tag(ag),
                  f"상대방이 환불 처리에 합의 — {note[:100]}")
    tracking.schedule(case)
    if tracking.is_confirmation(mail.get("body", "")):
        tracking.mark_confirmed(case, note[:150], mail.get("path", ""))
    return "agreed"


def handle_reply(case: dict, mail: dict) -> str:
    """상대방 회신 처리 — 수락/부분/거부/모호 4분기. 반환: action."""
    body = mail.get("body", "")
    low = body.lower()
    pb = cases.playbook_of(case)
    amount = case["intent"].get("amount") or 0

    # ① 완료 통보 (이미 추적 중 포함)
    if tracking.is_confirmation(body):
        cases.add_round(case, "in", f"상대방 완료 통보: {body[:100]}", mail.get("path", ""))
        tracking.mark_confirmed(case, body[:150], mail.get("path", ""))
        if case["status"] != "tracking":
            tracking.schedule(case)
        return "confirmed"

    # ② 수락
    if any(s in body for s in ACCEPT_SIGNALS):
        return _agree(case, mail, body.splitlines()[0] if body else "수락")

    # ③ 부분 제안 — 금액 판단은 고객 몫 (90% 이상만 자동 수락)
    offered = None
    m = _PARTIAL_WON.search(body)
    if m:
        offered = int(m.group(1).replace(",", ""))
    else:
        m = _PARTIAL_PCT.search(body)
        if m and amount:
            offered = amount * int(m.group(1)) // 100
    if offered and amount and offered < amount:
        cases.add_round(case, "in", f"상대방 부분 제안: {offered:,}원 (요구 {amount:,}원)",
                        mail.get("path", ""))
        if offered >= amount * 0.9:
            case["intent"]["amount"] = offered
            return _agree(case, mail, f"부분 제안 {offered:,}원 수락 (요구액의 90% 이상)")
        cases.set_status(case, "awaiting_customer")
        flow.ask_customer(case["flow"],
                          f"상대방이 {offered:,}원(요구액 {amount:,}원의 {offered * 100 // amount}%)을 "
                          "제안했어요. ① 수락 ② 전액 재요구 ③ 에스컬레이션 중 "
                          "원하시는 번호로 회신해 주세요. (질문은 이번 1회로 묶었어요)")
        return "partial_offer"

    # ④ 거부 → 다음 라운드 또는 에스컬레이션 제안
    if any(s in body for s in REJECT_SIGNALS):
        cases.add_round(case, "in", f"상대방 거부: {body[:100]}", mail.get("path", ""))
        rounds = _round_count(case)
        if rounds >= pb.get("max_rounds", 5):
            cases.set_status(case, "awaiting_customer")
            flow.ask_customer(case["flow"],
                              f"상대방이 {rounds}회 요구에도 거부하고 있어요. "
                              f"다음 단계로 {pb.get('escalation', '분쟁조정')}을 추천해요. "
                              "\"에스컬레이션\" 또는 \"취소\"로 회신해 주세요.")
            return "escalation_proposed"
        _send_round(case, rounds + 1)
        return "next_round"

    # ⑤ 모호 — 리마인더
    cases.add_round(case, "in", f"상대방 회신(판단 불가): {body[:80]}", mail.get("path", ""))
    _send_round(case, max(_round_count(case), 1),
                extra="앞선 회신으로는 처리 여부를 확인하기 어려워 다시 요청드립니다. "
                      "수락/거부 여부를 명확히 회신 부탁드립니다.")
    return "reminder"


def customer_decision(case: dict, decision: str) -> str:
    """고객 회신(수락/전액 재요구/에스컬레이션/취소) 반영."""
    d = decision.strip()
    if d.startswith("1") or "수락" in d:
        return _agree(case, {"body": "", "path": ""}, "고객이 부분 제안 수락을 선택")
    if d.startswith("2") or "재요구" in d or "전액" in d:
        cases.set_status(case, "negotiating")
        _send_round(case, _round_count(case) + 1,
                    extra="고객은 부분 환불이 아닌 전액 환불을 원하며, 해당 제안은 수락되지 않았습니다.")
        return "next_round"
    if d.startswith("3") or "에스컬레이션" in d:
        pb = cases.playbook_of(case)
        cases.set_status(case, "handoff")
        from . import hitl
        hitl.request(case, f"에스컬레이션 진행: {pb.get('escalation', '분쟁조정 신청')}",
                     [f"{pb.get('escalation', '분쟁조정')} 접수 페이지 접속",
                      "케이스 라운드 기록(data/cases)과 증빙을 첨부해 신청서 작성",
                      "접수번호를 완료 보고에 입력"])
        return "escalated"
    if "취소" in d:
        from . import queue as queue_mod
        cases.set_status(case, "cancelled")
        flow.cancel(case["flow"], "고객 요청으로 협상을 중단했어요. 지금까지의 경과는 케이스에 보존되어 있어요.")
        for state in ("active", "pending"):
            for it in common.list_queue(state):
                if it.get("case") == case["id"]:
                    queue_mod.cancel(it["id"])
        return "cancelled"
    return "noop"
