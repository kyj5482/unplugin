"""HITL — 사람 개입 계층 (TC-STR-005, TC-DEL-004 ⑤, TC-DEL-012 Takeover).

대부분의 업무는 LLM 에이전트가 수행하고, 봇 차단·본인 인증·2FA처럼
사람만 할 수 있는 지점에서만 개입을 요청한다. 코디네이터(agents: coordinator)가
직원(또는 대표)이 그대로 따라 할 수 있는 **클릭 단위 가이드**를 발행하고,
완료 보고(접수번호 등)를 받아 케이스를 자동 재개한다.

파일: data/handoff/<id>.md (가이드) + data/handoff/<id>.json (상태)
상태: open → done | abandoned

Takeover 모드(kind="takeover"): 고객 본인이 로그인·결제정보를 직접 입력하는
구간. 가이드에 "기록 중지" 구간이 명시되고, 해당 구간의 화면·입력은
어디에도 기록하지 않는다. 재개 불가 시 진행 상황을 보존한 채 재시작 경로 안내.

공개 인터페이스:
  request(case, reason, steps, kind="manual") -> handoff_id
  list_open() -> list[dict]
  complete(handoff_id, note, confirmation_no="") -> dict | None
  abandon(handoff_id, reason) -> dict | None
"""
from __future__ import annotations

from . import agents, common, flow

_GUIDE = """# 사람 개입 가이드: {title}

- **ID**: {hid}
- **케이스**: {case_id} ({case_type})
- **고객**: {customer}
- **담당 코디네이터**: {coordinator}
- **사유**: {reason}
- **종류**: {kind_label}
- **발행**: {ts}

## 따라 하기 (클릭 단위)

{steps}

{takeover_note}
## 완료 보고

처리 후 아래 명령으로 결과를 입력하세요 (접수번호가 있으면 함께):

```
python3 -m core hitl-done {hid} --note "처리 내용" --confirmation "접수번호"
```

보고 즉시 케이스가 자동 재개되어 다음 단계(완료 추적)로 넘어갑니다.
"""

_TAKEOVER_NOTE = """## ⚠ 기록 중지 구간 (Takeover)

로그인·인증·결제정보 입력 구간은 **고객 본인이 직접 입력**합니다.
- 이 구간 동안 화면 캡처·키 입력 기록을 하지 않습니다.
- 입력이 끝나면 고객이 "완료"라고 알려준 뒤에만 이어서 진행합니다.
- 재개가 불가능해지면 지금까지의 진행 상황은 케이스에 보존되어 있으니,
  가이드 1단계부터 다시 시작하면 됩니다 (중복 신청 여부를 먼저 확인).

"""


def _paths(hid: str):
    return common.HANDOFF / f"{hid}.md", common.HANDOFF / f"{hid}.json"


def request(case: dict, reason: str, steps: list[str],
            kind: str = "manual") -> str:
    """가이드 발행 + 케이스 handoff 전환 + Flow 기록. 반환: handoff id."""
    from . import cases as cases_mod
    common.ensure_dirs()
    hid = f"ho-{common.ts()}-{common.slug(case['type'], 16)}"
    coordinator = agents.assign("coordinator")
    guide_md, state_json = _paths(hid)
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    guide_md.write_text(_GUIDE.format(
        title=case["intent"].get("merchant", case["type"]),
        hid=hid, case_id=case["id"], case_type=case["type"],
        customer=case["customer"], coordinator=coordinator["name"],
        reason=reason, ts=common.iso(),
        kind_label="Takeover(고객 직접 입력)" if kind == "takeover" else "직원 수동 처리",
        steps=numbered,
        takeover_note=_TAKEOVER_NOTE if kind == "takeover" else "",
    ), encoding="utf-8")
    common.write_json(state_json, {
        "id": hid, "case": case["id"], "kind": kind, "status": "open",
        "reason": reason, "coordinator": coordinator["id"],
        "created": common.iso(), "resumed_status": "tracking",
    })
    cases_mod.set_status(case, "handoff")
    cases_mod.add_round(case, "sys", f"사람 개입 요청({kind}): {reason} — 가이드 {guide_md.name}")
    flow.add_step(case["flow"], agents.tag(coordinator),
                  f"사람 개입 가이드 발행: {reason} — {guide_md.name} "
                  f"(처리 후 `hitl-done {hid}`로 보고하면 자동 재개)")
    return hid


def request_for_item(item: dict, reason: str, steps: list[str],
                     kind: str = "manual") -> str:
    """케이스가 아닌 일반 큐 아이템의 사람 개입 — 완료 보고 시 아이템을 완결한다."""
    common.ensure_dirs()
    hid = f"ho-{common.ts()}-{common.slug(item['summary'], 16)}"
    coordinator = agents.assign("coordinator")
    guide_md, state_json = _paths(hid)
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    guide_md.write_text(_GUIDE.format(
        title=item["summary"], hid=hid, case_id=item["id"], case_type=item.get("kind", ""),
        customer=item["customer"], coordinator=coordinator["name"],
        reason=reason, ts=common.iso(),
        kind_label="Takeover(고객 직접 입력)" if kind == "takeover" else "직원 수동 처리",
        steps=numbered,
        takeover_note=_TAKEOVER_NOTE if kind == "takeover" else "",
    ), encoding="utf-8")
    common.write_json(state_json, {
        "id": hid, "item": item["id"], "kind": kind, "status": "open",
        "reason": reason, "coordinator": coordinator["id"], "created": common.iso(),
    })
    flow.add_step(item["flow"], agents.tag(coordinator),
                  f"사람 개입 가이드 발행: {reason} — {guide_md.name} "
                  f"(처리 후 `hitl-done {hid}`로 보고하면 자동 완결)")
    return hid


def list_open() -> list[dict]:
    if not common.HANDOFF.exists():
        return []
    out = []
    for p in sorted(common.HANDOFF.glob("*.json")):
        st = common.read_json(p)
        if st.get("status") == "open":
            out.append(st)
    return out


def _load(hid: str) -> dict | None:
    _, state_json = _paths(hid)
    return common.read_json(state_json) if state_json.exists() else None


def complete(hid: str, note: str, confirmation_no: str = "") -> dict | None:
    """사람 처리 완료 보고 → 증빙 기록 + 케이스/아이템 자동 재개."""
    from . import cases as cases_mod, queue, tracking
    st = _load(hid)
    if not st or st["status"] != "open":
        return None
    st["status"] = "done"
    st["note"] = common.mask_sensitive(note)
    st["confirmation_no"] = confirmation_no
    st["done_at"] = common.iso()
    common.write_json(_paths(hid)[1], st)

    if st.get("item"):
        queue.finish_after_hitl(st["item"], note, confirmation_no)
        return st

    case = cases_mod.load(st["case"])
    if case:
        receipt = common.EVIDENCE / case["id"] / f"manual-{common.ts()}.json"
        common.write_json(receipt, {
            "mode": "human", "handoff": hid, "note": st["note"],
            "confirmation_no": confirmation_no, "ts": common.iso()})
        cases_mod.add_evidence(case, str(receipt), f"사람 처리 완료 보고 ({hid})")
        cases_mod.add_round(case, "sys",
                            f"사람 처리 완료: {st['note']}"
                            + (f" / 접수번호 {confirmation_no}" if confirmation_no else ""))
        flow.add_step(case["flow"], "it/haru",
                      f"사람 개입 완료 보고 수신 — {st['note']}"
                      + (f" (접수번호 {confirmation_no})" if confirmation_no else ""))
        tracking.schedule(case)
    return st


def abandon(hid: str, reason: str) -> dict | None:
    """사람 처리 불가 보고 — 케이스를 '확인 필요'로 두고 고객에게 선택지 안내."""
    from . import cases as cases_mod
    st = _load(hid)
    if not st or st["status"] != "open":
        return None
    st["status"] = "abandoned"
    st["note"] = reason
    common.write_json(_paths(hid)[1], st)
    case = cases_mod.load(st["case"])
    if case:
        cases_mod.set_status(case, "awaiting_customer")
        flow.ask_customer(case["flow"],
                          f"사람 처리 단계에서 진행이 어려웠어요. 사유: {reason} / "
                          "대안: ① 다른 경로로 재시도 ② 고객님이 직접 처리(가이드 제공) ③ 취소. "
                          "원하시는 번호로 회신해 주세요.")
    return st
