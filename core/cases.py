"""케이스 저장소 — 스트레스 업무(환불·분쟁·해지)의 수명주기 관리 (TC-STR-002~006).

케이스는 "요청 접수"가 아니라 "결과 확인(입금 등)"까지가 완료다.
파일: data/cases/<id>.json

상태 전이:
  open → negotiating / portal_submitted → tracking → resolved
                     ↘ handoff(사람 개입) → (재개) ↗
  어느 상태든 → failed / cancelled

필드:
  id, customer, flow, type(플레이북 id), channel, intent{...},
  status, priority, assignee, rounds[], evidence[], tracking{...},
  created, updated
"""
from __future__ import annotations

from . import agents, common, stress

OPEN_STATES = ("open", "negotiating", "awaiting_customer", "portal_submitted",
               "handoff", "tracking")


def case_path(case_id: str):
    return common.CASES / f"{case_id}.json"


def create(customer_id: str, flow_id: str, playbook: dict, intent: dict,
           request_text: str) -> dict:
    """케이스 생성 + 담당 에이전트 배정. 스트레스 유형은 항상 우선순위 high."""
    common.ensure_dirs()
    cid = f"case-{common.ts()}-{common.slug(playbook['id'], 20)}"
    role = "negotiator" if playbook["channel"] == "email" else "resolver"
    agent = agents.assign(role)
    case = {
        "id": cid,
        "customer": customer_id,
        "flow": flow_id,
        "type": playbook["id"],
        "channel": playbook["channel"],
        "intent": intent,
        "request": common.mask_sensitive(request_text)[:500],
        "status": "open",
        "priority": "high",
        "assignee": agent["id"],
        "rounds": [],
        "evidence": [],
        "tracking": {"confirmed": False, "nudges": 0, "expected_by": None},
        "created": common.iso(),
        "updated": common.iso(),
    }
    save(case)
    return case


def save(case: dict) -> None:
    case["updated"] = common.iso()
    common.write_json(case_path(case["id"]), case)


def load(case_id: str) -> dict | None:
    p = case_path(case_id)
    return common.read_json(p) if p.exists() else None


def list_cases(status: str | None = None) -> list[dict]:
    if not common.CASES.exists():
        return []
    out = [common.read_json(p) for p in sorted(common.CASES.glob("*.json"))]
    if status == "open":
        return [c for c in out if c["status"] in OPEN_STATES]
    if status:
        return [c for c in out if c["status"] == status]
    return out


def by_flow(flow_id: str) -> dict | None:
    for c in list_cases():
        if c.get("flow") == flow_id:
            return c
    return None


def add_round(case: dict, direction: str, summary: str,
              mail_path: str = "") -> None:
    """협상·접수 라운드 기록. direction: out(우리→상대) | in(상대→우리) | sys."""
    case["rounds"].append({
        "ts": common.iso(), "direction": direction,
        "summary": common.mask_sensitive(summary), "mail": str(mail_path),
    })
    save(case)


def add_evidence(case: dict, path: str, note: str = "") -> None:
    case["evidence"].append({"path": str(path), "note": note, "ts": common.iso()})
    save(case)


def set_status(case: dict, status: str) -> None:
    case["status"] = status
    save(case)


def playbook_of(case: dict) -> dict:
    pb = stress.playbook(case["type"])
    if pb is None:
        raise ValueError(f"알 수 없는 케이스 유형: {case['type']}")
    return pb
