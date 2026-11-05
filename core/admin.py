"""admin.py — 피벗 운영자(Admin) 대시보드 (data/admin.html, 로컬 전용·비공개).

대행 운영판(core/dashboard.py — Flow·큐 중심)과 달리, 피벗 지표를 본다:
  ① 고객별 시간 배당 잔고 (절약 분·아낀 감정·적립 건수·개인 보정 time_factor)
  ② 최근 보고 수신 피드 (어떤 에이전트 발신 → 유형 매칭 → 적립량·산정 근거)
  ③ 무브먼트 제안/전환 현황 (임계치 대비 진행률)
  ④ 팁 발송 현황 (outbox의 팁 카드 집계)
  ⑤ 커뮤니티 그룹 현황 (core/community.py)
  ⑥ 미매칭 보고 (기본값 적립) — 분류기·카탈로그 개선 백로그

공개 인터페이스: generate() -> Path
고객 데이터가 포함되므로 생성물은 비공개(로컬 전용). 외부 JS 없음.
"""
from __future__ import annotations

import html as _html
from pathlib import Path

from . import common, community, dividend

ADMIN_HTML = "admin.html"

_CSS = """
:root{--g:#1c7544;--a:#c97840;--bg:#f6f4ec;--ink:#17211a;--line:#e3ded0;}
*{box-sizing:border-box}body{margin:0;font-family:Pretendard,-apple-system,'Apple SD Gothic Neo',
sans-serif;background:var(--bg);color:var(--ink);padding:28px clamp(16px,4vw,48px)}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px;color:var(--g)}
.sub{color:#6b7568;font-size:12.5px;margin-bottom:18px}
.tiles{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0 6px}
.tile{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 18px;min-width:150px}
.tile b{display:block;font-size:21px;color:var(--g)}.tile span{font-size:12px;color:#6b7568}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid var(--line);
border-radius:12px;overflow:hidden;font-size:13px}
th{background:#edeadd;text-align:left;padding:8px 12px;font-size:12px}
td{padding:8px 12px;border-top:1px solid var(--line);vertical-align:top}
.bar{background:#edeadd;border-radius:99px;height:8px;min-width:120px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--g)}
.amber{color:var(--a)}.muted{color:#8a927f;font-size:12px}
.dot{color:var(--a);letter-spacing:1px}
.pill{display:inline-block;background:#e8f0e9;color:var(--g);border-radius:99px;
padding:1px 9px;font-size:11.5px;margin-right:4px}
.warn{background:#f7ead9;color:#8a5a23}
"""


def _esc(s) -> str:
    return _html.escape(str(s))


def _agent_of(sender: str) -> str:
    """보고 발신 주소 → 에이전트 표시명 (muze@… → Muze)."""
    local = (sender or "").split("@")[0].lower()
    for name in ("muze", "dots", "chatgpt", "claude", "gemini"):
        if name in local:
            return name.capitalize()
    return sender or "?"


def _tip_mails() -> list[dict]:
    mails = []
    for p in sorted(common.OUTBOX.glob("*.md")):
        try:
            m = common.parse_mail(p)
        except ValueError:
            continue
        if "위임 팁" in m["subject"] or "더 좋은 방법을 알려드려요" in m["body"][:200]:
            mails.append(m)
    return mails


def _rows(customers: dict) -> tuple[list, list, list, int, int, int]:
    """고객 테이블 행 + 보고 피드 + 미매칭 목록 + 합계."""
    bal_rows, feed, unmatched = [], [], []
    tot_min = tot_emo = tot_ev = 0
    for cid in dividend.all_customers():
        led = dividend.load_ledger(cid)
        prof = customers.get(cid, {})
        t = led["totals"]
        tot_min += t["saved_minutes"]; tot_emo += t["emotion_saved"]; tot_ev += t["events_count"]
        thr = int(prof.get("movement_threshold_minutes", dividend.DEFAULT_THRESHOLD))
        prog = min(100, round(t["saved_minutes"] % thr / thr * 100)) if thr else 0
        sug = led.get("last_suggested_at_minutes", 0) // thr if thr else 0
        bal_rows.append({
            "cid": cid, "name": prof.get("name", cid),
            "region": prof.get("region", "-"),
            "factor": dividend.clamp_factor(prof.get("time_factor", 1.0)),
            "minutes": t["saved_minutes"], "emotion": t["emotion_saved"],
            "events": t["events_count"], "threshold": thr, "progress": prog,
            "suggests": sug,
        })
        for e in led["events"]:
            row = {"cid": cid, **e}
            feed.append(row)
            if not e.get("matched"):
                unmatched.append(row)
    feed.sort(key=lambda e: e.get("date", ""), reverse=True)
    return bal_rows, feed, unmatched, tot_min, tot_emo, tot_ev


def generate() -> Path:
    common.ensure_dirs()
    customers = common.load_profiles()
    bal, feed, unmatched, tot_min, tot_emo, tot_ev = _rows(customers)
    tips = _tip_mails()
    groups = community.memberships()
    h, mm = divmod(tot_min, 60)

    out = [f"<!doctype html><meta charset='utf-8'><title>Unplugin Admin — 시간 배당</title>",
           f"<style>{_CSS}</style>",
           "<h1>Unplugin Admin — 시간 배당 운영판</h1>",
           f"<div class='sub'>생성 {common.iso()} · 로컬 전용(고객 데이터 포함) · "
           "산정 근거: ops/research-time-baselines.md</div>",
           "<div class='tiles'>",
           f"<div class='tile'><b>{h}시간 {mm}분</b><span>전체 적립 잔고</span></div>",
           f"<div class='tile'><b>{tot_emo}</b><span>아낀 감정(합)</span></div>",
           f"<div class='tile'><b>{tot_ev}건</b><span>보고 적립</span></div>",
           f"<div class='tile'><b>{len(tips)}통</b><span>팁 카드 발송</span></div>",
           f"<div class='tile'><b>{len(groups)}개</b><span>커뮤니티 그룹</span></div>",
           "</div>"]

    # ① 고객별 잔고
    out.append("<h2>① 고객별 시간 배당 잔고</h2><table><tr><th>고객</th><th>지역</th>"
               "<th>잔고</th><th>감정</th><th>적립</th><th>보정</th>"
               "<th>임계치 진행</th><th>제안</th></tr>")
    for r in bal:
        bh, bm = divmod(r["minutes"], 60)
        out.append(
            f"<tr><td>{_esc(r['name'])} <span class='muted'>{_esc(r['cid'])}</span></td>"
            f"<td>{_esc(r['region'])}</td><td><b>{bh}시간 {bm}분</b></td>"
            f"<td class='amber'>{r['emotion']}</td><td>{r['events']}건</td>"
            f"<td>×{r['factor']:g}</td>"
            f"<td><div class='bar'><i style='width:{r['progress']}%'></i></div>"
            f"<span class='muted'>{r['progress']}% / {r['threshold']}분</span></td>"
            f"<td>{r['suggests']}회</td></tr>")
    if not bal:
        out.append("<tr><td colspan=8 class='muted'>적립 고객 없음</td></tr>")
    out.append("</table>")

    # ② 보고 수신 피드
    out.append("<h2>② 최근 보고 수신 피드</h2><table><tr><th>일시</th><th>고객</th>"
               "<th>에이전트</th><th>업무</th><th>적립</th><th>산정 근거</th></tr>")
    for e in feed[:20]:
        basis = e.get("basis", {})
        btxt = (f"기준 {basis.get('baseline', '?')}분 × ×{basis.get('factor', 1):g} · "
                f"{_esc(basis.get('evidence', ''))}") if basis else "-"
        mark = "" if e.get("matched") else " <span class='pill warn'>미매칭</span>"
        out.append(
            f"<tr><td class='muted'>{_esc(e.get('date', '')[:16])}</td>"
            f"<td>{_esc(e['cid'])}</td><td>{_esc(_agent_of(e.get('from', '')))}</td>"
            f"<td>{_esc(e['task'])}{mark}</td>"
            f"<td><b>+{e['saved_minutes']}분</b> <span class='dot'>"
            f"{dividend.emotion_dots(e['emotion_load'])}</span></td>"
            f"<td class='muted'>{btxt}</td></tr>")
    if not feed:
        out.append("<tr><td colspan=6 class='muted'>수신된 보고 없음</td></tr>")
    out.append("</table>")

    # ③ 무브먼트 현황
    out.append("<h2>③ 무브먼트 제안/전환 현황</h2><table><tr><th>고객</th>"
               "<th>제안 횟수</th><th>다음 제안까지</th></tr>")
    for r in bal:
        remain = r["threshold"] - r["minutes"] % r["threshold"]
        out.append(f"<tr><td>{_esc(r['name'])}</td><td>{r['suggests']}회</td>"
                   f"<td>{remain}분 더 적립 시</td></tr>")
    if not bal:
        out.append("<tr><td colspan=3 class='muted'>-</td></tr>")
    out.append("</table><div class='muted'>전환(실제 오프라인 실행) 실측은 CS 피드백 연동 예정 — ops/kpi.md ②.</div>")

    # ④ 팁 발송 현황
    out.append(f"<h2>④ 팁 카드 발송 — {len(tips)}통</h2><table><tr><th>일시</th>"
               "<th>수신</th><th>제목</th></tr>")
    for m in tips[-10:]:
        out.append(f"<tr><td class='muted'>{_esc(m['date'][:16])}</td>"
                   f"<td>{_esc(m['to'])}</td><td>{_esc(m['subject'])}</td></tr>")
    if not tips:
        out.append("<tr><td colspan=3 class='muted'>발송 없음</td></tr>")
    out.append("</table>")

    # ⑤ 커뮤니티 그룹
    out.append("<h2>⑤ 커뮤니티 그룹</h2><table><tr><th>그룹</th><th>인원</th>"
               "<th>멤버(익명)</th><th>지역 분포</th></tr>")
    profiles = customers
    for g, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        nicks = ", ".join(community.nickname(m["customer"], i)
                          for i, m in enumerate(members))
        regions: dict[str, int] = {}
        for m in members:
            rg = profiles.get(m["customer"], {}).get("region")
            if rg:
                regions[rg] = regions.get(rg, 0) + 1
        rtxt = " · ".join(f"{k} {v}" for k, v in sorted(regions.items())) or "-"
        mark = "" if len(members) >= community.MIN_GROUP else " <span class='pill warn'>인원 미달</span>"
        out.append(f"<tr><td>{_esc(community.GROUP_NAMES.get(g, g))}{mark}</td>"
                   f"<td>{len(members)}</td><td>{_esc(nicks)}</td><td>{_esc(rtxt)}</td></tr>")
    if not groups:
        out.append("<tr><td colspan=4 class='muted'>그룹 없음 — 적립이 쌓이면 자동 편성</td></tr>")
    out.append("</table>")

    # ⑥ 미매칭 보고 백로그
    out.append(f"<h2>⑥ 미매칭 보고 (기본값 적립) — {len(unmatched)}건</h2>"
               "<table><tr><th>일시</th><th>고객</th><th>제목</th><th>조치</th></tr>")
    for e in unmatched[:15]:
        out.append(f"<tr><td class='muted'>{_esc(e.get('date', '')[:16])}</td>"
                   f"<td>{_esc(e['cid'])}</td><td>{_esc(e.get('subject', ''))}</td>"
                   f"<td class='muted'>카탈로그 트리거 보강 후보</td></tr>")
    if not unmatched:
        out.append("<tr><td colspan=4 class='muted'>없음 — 분류 전부 매칭</td></tr>")
    out.append("</table>")

    path = common.DATA / ADMIN_HTML
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def calibrate(customer_id: str, factor: float) -> dict:
    """고객 개인 보정 계수 조정 (Admin 전용 — 고객에게 수동 기록을 시키지 않는다)."""
    p = common.CUSTOMERS / customer_id / "profile.json"
    if not p.exists():
        raise FileNotFoundError(f"고객 프로필 없음: {customer_id}")
    prof = common.read_json(p)
    prof["time_factor"] = dividend.clamp_factor(factor)
    common.write_json(p, prof)
    return prof
