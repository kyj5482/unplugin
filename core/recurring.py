"""반복 위임 — 자동 회차 실행 (TC-DEL-013).

"매주 생필품 주문" 같은 반복 위임을 등록하면, 서비스 틱마다 실행 시점이 된
회차를 자동 생성한다. 매 회차 결제 승인 게이트(TC-DEL-005)는 동일하게 적용되고,
회차별 Flow·사용량 차감이 기록되며, 고객이 일시정지·재개·해지할 수 있다.

파일: data/customers/<id>/recurring.json
공개 인터페이스:
  register(customer_id, summary, kind, interval_days, amount=0, est_hours=0) -> dict
  run_tick() -> int                     # 생성된 회차 수
  set_paused(customer_id, rec_id, paused) -> dict | None
  remove(customer_id, rec_id) -> bool
  list_for(customer_id) -> list[dict]
"""
from __future__ import annotations

from datetime import timedelta

from . import common, flow, queue


def _path(customer_id: str):
    return common.CUSTOMERS / customer_id / "recurring.json"


def list_for(customer_id: str) -> list[dict]:
    p = _path(customer_id)
    return common.read_json(p)["items"] if p.exists() else []


def _save(customer_id: str, items: list[dict]) -> None:
    common.write_json(_path(customer_id), {"items": items})


def register(customer_id: str, summary: str, kind: str, interval_days: int,
             amount: int = 0, est_hours: float = 0.0) -> dict:
    items = list_for(customer_id)
    rec = {
        "id": f"rec-{common.ts()}-{common.slug(summary, 16)}",
        "summary": summary, "kind": kind, "interval_days": interval_days,
        "amount": amount, "est_hours": est_hours,
        "next_at": common.iso(), "round": 0, "paused": False,
    }
    items.append(rec)
    _save(customer_id, items)
    return rec


def set_paused(customer_id: str, rec_id: str, paused: bool) -> dict | None:
    items = list_for(customer_id)
    for rec in items:
        if rec["id"] == rec_id:
            rec["paused"] = paused
            _save(customer_id, items)
            return rec
    return None


def remove(customer_id: str, rec_id: str) -> bool:
    items = list_for(customer_id)
    rest = [r for r in items if r["id"] != rec_id]
    if len(rest) == len(items):
        return False
    _save(customer_id, rest)
    return True


def run_tick() -> int:
    """실행 시점 도래 회차 생성 — 회차별 Flow + 큐 아이템 (승인 게이트 동일 적용)."""
    spawned = 0
    now_iso = common.iso()
    for prof in common.load_profiles().values():
        cid = prof["id"]
        items = list_for(cid)
        changed = False
        for rec in items:
            if rec.get("paused") or rec["next_at"] > now_iso:
                continue
            rec["round"] += 1
            rec["next_at"] = common.iso(common.now()
                                        + timedelta(days=rec["interval_days"]))
            changed = True
            fid = flow.create_flow(
                cid, f"{rec['summary']} ({rec['round']}회차)", "반복 위임",
                f"반복 위임 자동 실행 — {rec['interval_days']}일 주기, {rec['round']}회차")
            flow.add_step(fid, "concierge",
                          f"반복 위임 {rec['round']}회차 자동 생성 — 결제 승인 게이트는 "
                          "매 회차 동일 적용. 일시정지/해지는 이 메일에 회신으로 가능해요")
            queue.enqueue(cid, rec["kind"], f"{rec['summary']} ({rec['round']}회차)",
                          fid, amount=rec["amount"], est_hours=rec["est_hours"])
            spawned += 1
        if changed:
            _save(cid, items)
    return spawned
