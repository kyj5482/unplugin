"""고객 상태 메일 발송 (v0: data/outbox/ 파일로 시뮬레이션).

핵심 UX: 고객은 메일만으로 자기 일의 전체 흐름을 안다.
- 모든 Flow 전환마다 같은 스레드(thread=flow_id)로 상태 메일 발송
- 각 메일 하단에 지금까지의 타임라인 포함 (TC-EML-006)
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common

STATUS_ICON = {"접수": "📥", "진행 중": "⚙️", "확인 필요": "❓", "완료": "✅", "취소": "⛔", "격리": "🔒"}


def send(customer_id: str, subject: str, body: str, thread: str = "") -> Path | None:
    """고객의 실제 연락 주소로 메일 발송(outbox 기록). 프로필이 없으면 None."""
    prof = common.load_profiles().get(customer_id)
    if not prof:
        return None
    return common.write_outbox({
        "from": "agent@unplugin.me",
        "to": prof.get("contact") or prof.get("address", ""),
        "subject": f"[Unplugin] {subject}",
        "thread": thread,
        "body": body,
    })


def timeline_text(flow_path: Path) -> str:
    """Flow 문서의 처리 단계 표를 사람이 읽는 타임라인으로 변환."""
    if not Path(flow_path).exists():
        return ""
    lines = []
    in_table = False
    for raw in Path(flow_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## 처리 단계"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.startswith("|") and not re.match(r"^\|\s*[#-]", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 4 and cells[1] and cells[1] != "시각":
                lines.append(f"  · {cells[1]}  {cells[2]} — {cells[3]}")
    return "\n".join(lines)


def send_flow_update(customer_id: str, flow_id: str, flow_path: Path,
                     status: str, headline: str, detail: str = "") -> Path | None:
    """Flow 전환 상태 메일: 제목에 상태, 본문에 헤드라인 + 전체 타임라인."""
    icon = STATUS_ICON.get(status, "•")
    body_parts = [f"{icon} {headline}"]
    if detail:
        body_parts.append("\n" + detail)
    tl = timeline_text(flow_path)
    if tl:
        body_parts.append("\n— 지금까지의 진행 —\n" + tl)
    body_parts.append(f"\n이 메일 스레드 하나로 이 일의 처음부터 끝까지 확인하실 수 있어요. (Flow: {flow_id})")
    return send(customer_id, f"{headline} · {status}", "\n".join(body_parts), thread=flow_id)
