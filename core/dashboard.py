"""대표용 로컬 Unified View — flows/*.md + 큐 상태를 단일 HTML로.

공개 인터페이스:
  generate() -> Path   # data/dashboard.html (common.DASHBOARD) 생성 후 경로 반환

디자인: 홈페이지(docs/index.html)와 같은 언어 — 다크 배경(#0C1711→#13241A),
Pretendard, 그린(#2F6B4A)/앰버(#D89A5B) 포인트, 둥근 카드. 외부 JS 라이브러리 없음.
고객 데이터가 포함되므로 생성물은 비공개(로컬 전용).
"""
from __future__ import annotations

import html as _html
import re
from pathlib import Path

from . import common

# 상태 표시 순서 (요약 스탯·배지 공통)
STATUSES = ("접수", "진행 중", "확인 필요", "완료", "취소")
_STATUS_CLASS = {
    "접수": "st-new",
    "진행 중": "st-run",
    "확인 필요": "st-ask",
    "완료": "st-done",
    "취소": "st-cancel",
}

# ── Flow .md 파싱 (core/flow.py 포맷 기준) ─────────────────


def _field(text: str, name: str) -> str:
    m = re.search(rf"\*\*{re.escape(name)}\*\*:\s*(.*)", text)
    return m.group(1).strip() if m else ""


def _steps_of(text: str) -> list[dict]:
    """'## 처리 단계' 표의 데이터 행 → [{n, time, dept, content, artifact}]."""
    steps = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## 처리 단계"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if not (in_table and line.startswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("#", "") or set(cells[0]) <= {"-"}:
            continue  # 헤더/구분선
        steps.append({
            "n": cells[0], "time": cells[1], "dept": cells[2],
            "content": cells[3], "artifact": cells[4] if len(cells) > 4 else "",
        })
    return steps


def _questions_of(text: str) -> list[str]:
    """'## 확인 필요' 섹션의 리스트 항목."""
    m = re.search(r"## 확인 필요.*?\n(.*?)(?=\n## |\Z)", text, re.S)
    if not m:
        return []
    return [ln.strip()[2:].strip() for ln in m.group(1).splitlines()
            if ln.strip().startswith("- ")]


def _reclaimed_of(text: str) -> float | None:
    val = _field(text, "예상/실측 Reclaimed Hours")
    m = re.search(r"(\d+(?:\.\d+)?)", val)
    return float(m.group(1)) if m else None


def parse_flow_file(path: Path) -> dict | None:
    """flows/<id>.md → 대시보드용 dict. Flow 형식이 아니면 None."""
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"^# Flow: (.+)$", text, re.M)
    if not m:
        return None
    return {
        "id": Path(path).stem,
        "title": m.group(1).strip(),
        "customer": _field(text, "고객"),
        "kind": _field(text, "유형"),
        "received": _field(text, "접수"),
        "status": _field(text, "상태"),
        "steps": _steps_of(text),
        "questions": _questions_of(text),
        "reclaimed": _reclaimed_of(text),
    }


def load_flows() -> list[dict]:
    """flows/*.md (_template.md, README.md 제외) → 최신순 목록."""
    flows = []
    if common.FLOWS.exists():
        for p in sorted(common.FLOWS.glob("*.md")):
            if p.name in ("_template.md", "README.md"):
                continue
            f = parse_flow_file(p)
            if f:
                flows.append(f)
    flows.sort(key=lambda f: (f["received"], f["id"]), reverse=True)
    return flows


# ── HTML 렌더링 ──────────────────────────────────────────

_CSS = """
:root {
  --dark0:#0C1711; --dark1:#13241A;
  --w-ink:#F6F4EC; --w-ink2:#C3CDC4; --w-ink3:#93A096;
  --green:#2F6B4A; --green-deep:#1E4733; --green-soft:#7FC79B;
  --amber:#D89A5B; --amber-deep:#C97840;
  --hair:rgba(242,239,231,.12); --ease:cubic-bezier(.22,.61,.36,1);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family:"Pretendard Variable",Pretendard,"Apple SD Gothic Neo",sans-serif;
  background:linear-gradient(180deg,var(--dark0),var(--dark1)) fixed; color:var(--w-ink);
  line-height:1.6; -webkit-font-smoothing:antialiased; min-height:100vh;
}
.wrap { max-width:960px; margin:0 auto; padding:40px 24px 80px; }
header { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; margin-bottom:28px; }
.logo { font-weight:800; font-size:1.15rem; letter-spacing:-.02em; }
.logo i { font-style:normal; color:var(--amber); }
.logo span { font-weight:600; color:var(--w-ink3); font-size:.85rem; margin-left:10px; }
.gen { font-size:.78rem; color:var(--w-ink3); }

/* 요약 스탯 */
.stats { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:14px; }
.tile {
  border-radius:18px; padding:18px 20px 16px;
  background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.03));
  border:1px solid var(--hair);
}
.tile .tl { font-size:.76rem; font-weight:700; letter-spacing:.1em; color:var(--w-ink3); text-transform:uppercase; }
.tile .num { font-size:2.1rem; font-weight:800; letter-spacing:-.03em; line-height:1.25; font-variant-numeric:tabular-nums; }
.tile .num .unit { font-size:.95rem; font-weight:600; color:var(--w-ink2); margin-left:4px; }
.tile.hero .num { color:var(--amber); }
.tile .sub { font-size:.78rem; color:var(--w-ink3); }
.statusbar { display:flex; flex-wrap:wrap; gap:9px; margin-bottom:36px; }
.schip {
  display:inline-flex; align-items:center; gap:8px; font-size:.82rem; font-weight:600;
  color:var(--w-ink2); border:1px solid var(--hair); background:rgba(255,255,255,.05);
  border-radius:999px; padding:6px 14px;
}
.schip i { width:9px; height:9px; border-radius:50%; flex:none; }
.schip b { color:var(--w-ink); font-weight:800; font-variant-numeric:tabular-nums; }
.dot-new{background:#8B958D;} .dot-run{background:#E5AC6C;} .dot-ask{background:var(--amber);}
.dot-done{background:var(--green-soft);} .dot-cancel{background:#5C6A5F;}

/* 섹션 */
h2 { font-size:1.05rem; font-weight:800; letter-spacing:-.01em; margin:34px 0 14px; display:flex; align-items:center; gap:10px; }
h2 .cnt { font-size:.8rem; font-weight:700; color:var(--w-ink3); }
section.attention h2 { color:var(--amber); }
section.attention .card { border-color:rgba(216,154,91,.45); background:linear-gradient(160deg,rgba(216,154,91,.12),rgba(255,255,255,.03)); }
.toolrow { display:flex; justify-content:flex-end; margin:34px 0 -24px; }
.toolrow button {
  font:inherit; font-size:.78rem; font-weight:700; color:var(--w-ink2); cursor:pointer;
  background:rgba(255,255,255,.05); border:1px solid var(--hair); border-radius:999px; padding:6px 14px;
  transition:background .25s var(--ease);
}
.toolrow button:hover { background:rgba(255,255,255,.1); }

/* Flow 카드 */
.card {
  border-radius:18px; border:1px solid var(--hair); overflow:hidden;
  background:linear-gradient(160deg,rgba(255,255,255,.07),rgba(255,255,255,.025));
  margin-bottom:12px;
}
.card summary { list-style:none; cursor:pointer; padding:16px 20px; }
.card summary::-webkit-details-marker { display:none; }
.card summary:hover { background:rgba(255,255,255,.04); }
.crow1 { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.ctitle { font-weight:800; font-size:1rem; letter-spacing:-.01em; }
.ccust { font-size:.8rem; color:var(--w-ink3); }
.badge {
  font-size:.72rem; font-weight:700; padding:3px 11px; border-radius:999px; white-space:nowrap;
  border:1px solid var(--hair); color:var(--w-ink2); background:rgba(255,255,255,.07);
}
.badge.st-run  { color:#F3CFA6; background:rgba(216,154,91,.16); border-color:rgba(216,154,91,.3); }
.badge.st-ask  { color:#231306; background:var(--amber); border-color:var(--amber); }
.badge.st-done { color:#A9DDBE; background:rgba(92,168,124,.14); border-color:rgba(92,168,124,.3); }
.badge.st-cancel { color:var(--w-ink3); text-decoration:line-through; }
.chev { margin-left:auto; color:var(--w-ink3); font-size:.8rem; transition:transform .25s var(--ease); }
details[open] .chev { transform:rotate(90deg); }
.crow2 { margin-top:6px; font-size:.84rem; color:var(--w-ink2); display:flex; gap:10px; flex-wrap:wrap; }
.crow2 .meta { color:var(--w-ink3); white-space:nowrap; font-variant-numeric:tabular-nums; }
.cbody { padding:4px 20px 18px; border-top:1px solid var(--hair); }
.cbody h3 { font-size:.78rem; font-weight:700; letter-spacing:.08em; color:var(--w-ink3); margin:14px 0 8px; text-transform:uppercase; }
table.tl-table { width:100%; border-collapse:collapse; font-size:.84rem; }
table.tl-table th { text-align:left; font-size:.72rem; font-weight:700; color:var(--w-ink3); padding:6px 10px 6px 0; border-bottom:1px solid var(--hair); }
table.tl-table td { padding:7px 10px 7px 0; border-bottom:1px solid rgba(242,239,231,.06); vertical-align:top; color:var(--w-ink2); }
table.tl-table td.t-time { white-space:nowrap; color:var(--w-ink3); font-variant-numeric:tabular-nums; }
table.tl-table td.t-dept { font-weight:700; color:var(--green-soft); white-space:nowrap; }
.qlist { list-style:none; }
.qlist li { font-size:.84rem; color:#F3CFA6; padding:4px 0 4px 18px; position:relative; }
.qlist li::before { content:"?"; position:absolute; left:0; font-weight:800; color:var(--amber); }
.rh { font-size:.84rem; color:var(--w-ink2); margin-top:12px; }
.rh b { color:var(--amber); }
.empty { border:1px dashed var(--hair); border-radius:18px; padding:28px; text-align:center; color:var(--w-ink3); font-size:.88rem; }
footer { margin-top:48px; font-size:.75rem; color:var(--w-ink3); text-align:center; }
@media (max-width:640px) { .stats { grid-template-columns:1fr; } }
"""


def _esc(s: str) -> str:
    return _html.escape(str(s), quote=True)


def _badge(status: str) -> str:
    cls = _STATUS_CLASS.get(status, "st-new")
    return f'<span class="badge {cls}">{_esc(status or "접수")}</span>'


def _fmt_hours(v: float) -> str:
    return f"{v:g}"


def _card(f: dict) -> str:
    last = f["steps"][-1]["content"] if f["steps"] else "기록된 단계 없음"
    rows = "".join(
        f'<tr><td>{_esc(s["n"])}</td><td class="t-time">{_esc(s["time"])}</td>'
        f'<td class="t-dept">{_esc(s["dept"])}</td><td>{_esc(s["content"])}</td>'
        f'<td>{_esc(s["artifact"])}</td></tr>'
        for s in f["steps"]
    ) or '<tr><td colspan="5">아직 기록된 단계가 없어요.</td></tr>'
    qs = ""
    if f["questions"]:
        qs = ('<h3>확인 필요</h3><ul class="qlist">'
              + "".join(f"<li>{_esc(q)}</li>" for q in f["questions"]) + "</ul>")
    rh = ""
    if f["reclaimed"] is not None:
        rh = f'<p class="rh">Reclaimed Hours: <b>{_fmt_hours(f["reclaimed"])}h</b></p>'
    received = _esc(f["received"][:16].replace("T", " "))
    return f"""<details class="card">
  <summary>
    <div class="crow1">
      <span class="ctitle">{_esc(f["title"])}</span>
      <span class="ccust">{_esc(f["customer"])} · {_esc(f["kind"])}</span>
      {_badge(f["status"])}
      <span class="chev">▸</span>
    </div>
    <div class="crow2">
      <span>{_esc(last)}</span>
      <span class="meta">단계 {len(f["steps"])} · 접수 {received}</span>
    </div>
  </summary>
  <div class="cbody">
    <h3>타임라인</h3>
    <table class="tl-table">
      <thead><tr><th>#</th><th>시각</th><th>부문</th><th>수행 내용</th><th>산출물/링크</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    {qs}{rh}
  </div>
</details>"""


def render(flows: list[dict], queue_counts: dict[str, int]) -> str:
    counts = {s: 0 for s in STATUSES}
    other = 0
    total_rh = 0.0
    for f in flows:
        if f["status"] in counts:
            counts[f["status"]] += 1
        else:
            other += 1
        if f["reclaimed"] is not None:
            total_rh += f["reclaimed"]

    attention = [f for f in flows if f["status"] == "확인 필요"]
    rest = [f for f in flows if f["status"] != "확인 필요"]

    chips = "".join(
        f'<span class="schip"><i class="dot-{_STATUS_CLASS[s].removeprefix("st-")}"></i>'
        f'{_esc(s)} <b data-stat="{_esc(s)}">{counts[s]}</b></span>'
        for s in STATUSES
    )
    if other:
        chips += f'<span class="schip"><i class="dot-new"></i>기타 <b>{other}</b></span>'

    att_html = ""
    if attention:
        att_html = (
            f'<section class="attention" id="attention">'
            f'<h2>확인 필요 — 대표 답변 대기 <span class="cnt">{len(attention)}건</span></h2>'
            + "".join(_card(f) for f in attention) + "</section>"
        )

    if rest:
        rest_html = "".join(_card(f) for f in rest)
    elif not attention:
        rest_html = '<div class="empty">아직 기록된 Flow가 없어요. 첫 요청이 접수되면 여기에 나타납니다.</div>'
    else:
        rest_html = '<div class="empty">확인 필요 외의 Flow가 없어요.</div>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Unplugin — Unified View</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="logo">un<i>plugin</i><span>Unified View · 대표 전용</span></div>
  <div class="gen">생성 {_esc(common.iso())}</div>
</header>

<div class="stats">
  <div class="tile"><div class="tl">전체 Flow</div>
    <div class="num" data-stat="total">{len(flows)}</div>
    <div class="sub">flows/ 기준 전 업무</div></div>
  <div class="tile hero"><div class="tl">Reclaimed Hours 합계</div>
    <div class="num"><span data-stat="reclaimed">{_fmt_hours(total_rh)}</span><span class="unit">h</span></div>
    <div class="sub">고객에게 되돌려준 시간</div></div>
  <div class="tile"><div class="tl">큐</div>
    <div class="num"><span data-stat="pending">{queue_counts.get("pending", 0)}</span><span class="unit">대기</span>
      · <span data-stat="active">{queue_counts.get("active", 0)}</span><span class="unit">진행</span></div>
    <div class="sub">data/queue/pending · active</div></div>
</div>
<div class="statusbar">{chips}</div>

{att_html}

<div class="toolrow"><button type="button" id="toggleAll" data-open="0">모두 펼치기</button></div>
<section id="flows">
<h2>Flow 목록 <span class="cnt">최신순</span></h2>
{rest_html}
</section>

<footer>고객 데이터 포함 — 외부 공유 금지 · python3 -m core dashboard 로 갱신</footer>
</div>
<script>
const btn = document.getElementById('toggleAll');
btn.addEventListener('click', () => {{
  const open = btn.dataset.open !== '1';
  document.querySelectorAll('details.card').forEach(d => d.open = open);
  btn.dataset.open = open ? '1' : '0';
  btn.textContent = open ? '모두 접기' : '모두 펼치기';
}});
</script>
</body>
</html>
"""


def generate() -> Path:
    """flows/ + 큐 상태를 읽어 data/dashboard.html 생성, 경로 반환."""
    common.ensure_dirs()
    flows = load_flows()
    queue_counts = {}
    for state in ("pending", "active"):
        try:
            queue_counts[state] = len(common.list_queue(state))
        except Exception:
            queue_counts[state] = 0
    out = common.DASHBOARD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(flows, queue_counts), encoding="utf-8")
    return out
