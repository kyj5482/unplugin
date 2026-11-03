"""자사 서비스 해지·환불 — 시점별 규정 적용 (TC-OPS-005, ops/pricing.md).

규정 (ops/pricing.md "해지·환불 규정" — 온보딩 환영 메일에서 사전 고지):
  · 수행 전(이번 달 위임 사용 0h): 당월 요금 전액 환불
  · 수행 중(사용량 있음): 미사용분 일할 — 사용 비율만큼 차감 후 환불
  · 완료 후: 당월 환불 없음, 분쟁은 CS 접수 → 대표 검토(3영업일) 절차

공개 인터페이스:
  cancel_service(customer_id, monthly_fee) -> dict
"""
from __future__ import annotations

from . import common, flow, notify

TIER_FEES = {"one": 19000, "flow": 59000, "life": 149000}  # ops/pricing.md 초안 티어


def _month_usage(customer_id: str) -> float:
    from . import queue
    p = queue.usage_path(customer_id)
    if not p.exists():
        return 0.0
    return float(common.read_json(p)["monthly"].get(common.now().strftime("%Y-%m"), 0.0))


def cancel_service(customer_id: str, monthly_fee: int | None = None) -> dict:
    """월 중 해지 처리 — 시점별 환불 계산 + Flow 기록 + 고객 안내."""
    prof = common.load_profiles().get(customer_id)
    if not prof:
        return {"ok": False, "reason": f"고객 없음: {customer_id}"}
    from . import queue
    fee = monthly_fee or TIER_FEES.get(prof.get("tier", "one"), 49000)
    used = _month_usage(customer_id)
    limit = queue.TIER_HOURS.get(prof.get("tier", "one"), 10.0)

    if used <= 0:
        refund, stage = fee, "수행 전 — 전액 환불"
    elif used < limit:
        refund = int(fee * (1 - used / limit))
        stage = f"수행 중 — 미사용분 일할 환불 (사용 {used:g}h/{limit:g}h)"
    else:
        refund, stage = 0, "완료 후 — 당월 환불 없음 (분쟁은 CS 접수 → 대표 검토 3영업일)"

    fid = flow.create_flow(customer_id, "서비스 해지·환불", "해지",
                           f"월 중 해지 요청 — {stage}")
    flow.add_step(fid, "cs",
                  f"해지 접수 — 규정({stage}) 적용: 환불 {refund:,}원 / 월 요금 {fee:,}원. "
                  "규정은 온보딩 환영 메일에서 사전 고지됨 (ops/pricing.md)",
                  notify_customer=False)
    flow.set_status(fid, "완료")
    notify.send(customer_id, "해지 및 환불 처리 안내", "\n".join([
        f"{prof.get('name', customer_id)}님, 해지 요청을 처리했어요.",
        f"- 적용 규정: {stage}",
        f"- 환불 금액: {refund:,}원 (3영업일 내 결제 수단으로 환급)",
        "- 규정 전문: 가입 시 환영 메일과 ops/pricing.md에 사전 고지된 내용과 동일해요.",
        "그동안 함께해 주셔서 감사했어요. 언제든 다시 돌아오실 수 있어요.",
    ]), thread=fid)
    return {"ok": True, "refund": refund, "stage": stage, "flow": fid}
