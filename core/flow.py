"""Flow 엔진 — 모든 업무의 Unified View (flows/*.md) + 전환마다 고객 상태 메일.

공개 인터페이스 (다른 모듈은 이것만 사용):
  create_flow(customer_id, title, kind, request_text) -> flow_id
  add_step(flow_id, dept, content, handoff=None, notify_customer=True)
  ask_customer(flow_id, question)
  complete(flow_id, summary, reclaimed_hours=None)
  cancel(flow_id, reason)
  set_status(flow_id, status)
  flow_path(flow_id) -> Path
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, notify

_TEMPLATE = """# Flow: {title}

- **ID**: {fid}
- **고객**: {customer}
- **유형**: {kind}
- **접수**: {received}
- **상태**: 접수

## 요청 원문

> {request}

## 처리 단계

| # | 시각 | 부문 | 수행 내용 | 산출물/링크 |
|---|------|------|-----------|-------------|

## 핸드오프

## 확인 필요 (대표/고객 질문)

## 결과 요약

- **산출물**:
- **예상/실측 Reclaimed Hours**:
- **다음 단계 제안**:
"""


def flow_path(flow_id: str) -> Path:
    return common.FLOWS / f"{flow_id}.md"


def _read(flow_id: str) -> str:
    return flow_path(flow_id).read_text(encoding="utf-8")


def _write(flow_id: str, text: str) -> None:
    flow_path(flow_id).write_text(text, encoding="utf-8")


def _customer_of(flow_id: str) -> str:
    m = re.search(r"\*\*고객\*\*: (\S+)", _read(flow_id))
    return m.group(1) if m else ""


def _title_of(flow_id: str) -> str:
    m = re.search(r"^# Flow: (.+)$", _read(flow_id), re.M)
    return m.group(1).strip() if m else flow_id


def status_of(flow_id: str) -> str:
    m = re.search(r"\*\*상태\*\*: (.+)", _read(flow_id))
    return m.group(1).strip() if m else ""


def set_status(flow_id: str, status: str) -> None:
    _write(flow_id, re.sub(r"(\*\*상태\*\*: ).+", rf"\g<1>{status}", _read(flow_id)))


def create_flow(customer_id: str, title: str, kind: str, request_text: str) -> str:
    common.FLOWS.mkdir(parents=True, exist_ok=True)
    base = f"{common.now():%Y-%m-%d}-{common.slug(title)}"
    fid, i = base, 1
    while flow_path(fid).exists():
        i += 1
        fid = f"{base}-{i}"
    _write(fid, _TEMPLATE.format(
        title=title, fid=fid, customer=customer_id, kind=kind,
        received=common.iso(), request=request_text.replace("\n", " ")[:300]))
    add_step(fid, "concierge", "접수·분류", notify_customer=False)
    notify.send_flow_update(customer_id, fid, flow_path(fid), "접수",
                            f"\"{title}\" 접수했어요", "담당 배분 후 바로 진행 상황을 이 스레드로 알려드릴게요.")
    return fid


def add_step(flow_id: str, dept: str, content: str,
             handoff: str | None = None, notify_customer: bool = True) -> None:
    text = _read(flow_id)
    rows = re.findall(r"^\| \d+ \|", text, re.M)
    row = f"| {len(rows) + 1} | {common.iso()} | {dept} | {content} |  |"
    idx = text.find("## 핸드오프")
    text = text[:idx].rstrip() + "\n" + row + "\n\n" + text[idx:]
    if handoff:
        hidx = text.find("## 확인 필요")
        text = text[:hidx].rstrip() + f"\n- {common.iso()} {handoff}\n\n" + text[hidx:]
    _write(flow_id, text)
    if status_of(flow_id) == "접수":
        set_status(flow_id, "진행 중")
    if notify_customer:
        notify.send_flow_update(_customer_of(flow_id), flow_id, flow_path(flow_id),
                                "진행 중", f"\"{_title_of(flow_id)}\" 진행 중", f"[{dept}] {content}")


def ask_customer(flow_id: str, question: str) -> None:
    text = _read(flow_id)
    idx = text.find("## 결과 요약")
    text = text[:idx].rstrip() + f"\n- {common.iso()} (고객) {question}\n\n" + text[idx:]
    _write(flow_id, text)
    set_status(flow_id, "확인 필요")
    notify.send_flow_update(_customer_of(flow_id), flow_id, flow_path(flow_id),
                            "확인 필요", f"\"{_title_of(flow_id)}\" 확인이 필요해요", question)


def complete(flow_id: str, summary: str, reclaimed_hours: float | None = None) -> None:
    text = _read(flow_id)
    text = text.replace("- **산출물**:", f"- **산출물**: {summary}", 1)
    if reclaimed_hours is not None:
        text = text.replace("- **예상/실측 Reclaimed Hours**:",
                            f"- **예상/실측 Reclaimed Hours**: {reclaimed_hours}", 1)
    _write(flow_id, text)
    add_step(flow_id, "concierge", f"완결: {summary}", notify_customer=False)
    set_status(flow_id, "완료")
    extra = f"\n이번 일로 약 {reclaimed_hours}시간이 비었어요. 그 시간, 화면 밖에서 쓰실 수 있게 추천을 준비할게요." if reclaimed_hours else ""
    notify.send_flow_update(_customer_of(flow_id), flow_id, flow_path(flow_id),
                            "완료", f"\"{_title_of(flow_id)}\" 완료", summary + extra)


def cancel(flow_id: str, reason: str) -> None:
    add_step(flow_id, "concierge", f"취소: {reason}", notify_customer=False)
    set_status(flow_id, "취소")
    notify.send_flow_update(_customer_of(flow_id), flow_id, flow_path(flow_id),
                            "취소", f"\"{_title_of(flow_id)}\" 취소됨", reason)
