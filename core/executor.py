"""실행기 — 큐 active 아이템의 수행 계층 (TC-DEL-010 지향, 증빙 있는 완료 보고).

기본은 v0 시뮬레이션(표준 라이브러리만 — 기존 동작과 동일한 수준).
대표 맥북에서:
    pip install playwright && playwright install chromium
후 환경변수 UNPLUGIN_REAL_BROWSER=1 이면, 플러그인 executor가 "browser"인
아이템을 headless chromium으로 실제 수행하고 증빙 스크린샷을
data/evidence/<item_id>/step1.png 에 남긴다.
playwright가 없으면 조용히 시뮬레이션으로 폴백한다 (선택 의존성).

공개 인터페이스:
  run(item, profile) -> {"ok", "summary", "evidence", "reclaimed", "mode"}
  evidence_note(result) -> str   (Flow 기록용 한 줄)
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote_plus

from . import classify, common

# 플러그인별 기본 진입점 — 카탈로그에 URL 필드가 없어 소수만 상수로 유지.
# item 본문/summary에 `url: <주소>` 가 있으면 그 주소가 우선.
DEFAULT_ENTRYPOINTS = {
    "price-compare": "https://search.danawa.com/dsearch.php?query={query}",
}
FALLBACK_SEARCH = "https://duckduckgo.com/?q={query}"

BROWSER_TIMEOUT_MS = 30_000  # 페이지 이동 타임아웃

# summary 끝의 요청 어투(검색어가 아님) 제거용
_REQUEST_SUFFIX = re.compile(
    r"\s*(최저가\s*)?(찾아\s*줘|찾아줘|찾기|알아봐\s*줘|알려\s*줘|알려줘|비교해\s*줘|비교해줘|"
    r"주문해\s*줘|주문해줘|예약해\s*줘|예약해줘|해\s*줘|해줘|부탁해요?|주세요)\s*$")
_URL_RE = re.compile(r"url:\s*(\S+)", re.IGNORECASE)


# ── 디스패치 ─────────────────────────────────────────────

def run(item: dict, profile: dict) -> dict:
    """아이템 1건 수행. 반환 계약:
    {"ok": bool, "summary": str, "evidence": [경로...],
     "reclaimed": float, "mode": "simulated"|"browser"}
    """
    plugin = _plugin_of(item)
    if _real_browser_ready() and plugin and plugin.get("executor") == "browser":
        return _run_browser(item, plugin, profile)
    return _run_simulated(item, plugin)


def _plugin_of(item: dict) -> dict | None:
    """item["kind"]가 "plugin:<id>"면 카탈로그에서 해당 플러그인 조회."""
    kind = item.get("kind", "") or ""
    if not kind.startswith("plugin:"):
        return None
    pid = kind.split(":", 1)[1]
    for pl in classify.load_catalog():
        if pl.get("id") == pid:
            return pl
    return None


def _real_browser_ready() -> bool:
    """env 켜져 있고 playwright import 가능할 때만 True (아니면 조용히 폴백)."""
    if os.environ.get("UNPLUGIN_REAL_BROWSER") != "1":
        return False
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


# ── 시뮬레이션 실행 (기존 v0 동작 수준) ───────────────────

def _run_simulated(item: dict, plugin: dict | None) -> dict:
    reclaimed = (item.get("est_hours")
                 or (plugin or {}).get("est_hours_per_week")
                 or 0.5)
    return {
        "ok": True,
        "summary": f"{item['summary']} 처리 완료 (v0 시뮬레이션 — 증빙 없음)",
        "evidence": [],
        "reclaimed": float(reclaimed),
        "mode": "simulated",
    }


# ── 브라우저 실행 (PoC — headless chromium + 증빙 스크린샷) ──

def _query_of(item: dict) -> str:
    """검색어는 item summary에서 추출 — 요청 어투·포워딩 접두는 제거."""
    q = (item.get("summary") or "").strip()
    q = re.sub(r"^(fwd|re):\s*", "", q, flags=re.IGNORECASE)
    prev = None
    while prev != q:  # "최저가 찾아줘" 같은 중첩 어미도 모두 제거
        prev = q
        q = _REQUEST_SUFFIX.sub("", q).strip()
    return q or (item.get("summary") or "").strip()


def _entry_url(item: dict, plugin: dict) -> str:
    text = f"{item.get('summary', '')}\n{item.get('body', '')}"
    m = _URL_RE.search(text)
    if m:
        return m.group(1)
    query = quote_plus(_query_of(item))
    tpl = DEFAULT_ENTRYPOINTS.get(plugin.get("id"), FALLBACK_SEARCH)
    return tpl.format(query=query)


def _rel(path) -> str:
    """증빙 경로를 가능하면 리포 루트 기준 상대 경로로 (보고 가독성)."""
    try:
        return str(path.relative_to(common.ROOT))
    except ValueError:
        return str(path)


def _run_browser(item: dict, plugin: dict, profile: dict) -> dict:
    url = _entry_url(item, plugin)
    evid_dir = common.DATA / "evidence" / item["id"]
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(BROWSER_TIMEOUT_MS)
                page.goto(url, wait_until="domcontentloaded",
                          timeout=BROWSER_TIMEOUT_MS)
                title = (page.title() or "").strip()
                try:
                    body_text = page.inner_text("body", timeout=5_000)
                except Exception:
                    body_text = ""
                snippet = " ".join(body_text.split())[:160]
                evid_dir.mkdir(parents=True, exist_ok=True)
                shot = evid_dir / "step1.png"
                page.screenshot(path=str(shot))
            finally:
                browser.close()
        reclaimed = float(item.get("est_hours")
                          or plugin.get("est_hours_per_week") or 0.5)
        summary = (f"{item['summary']} — 브라우저 수행 완료: 페이지 \"{title}\" ({url})"
                   + (f" / 대표 내용: {snippet}" if snippet else "")
                   + f" / 증빙: {_rel(shot)}")
        return {"ok": True, "summary": summary, "evidence": [str(shot)],
                "reclaimed": reclaimed, "mode": "browser"}
    except Exception as e:  # 타임아웃 포함 — 큐의 기존 실패 규칙으로 위임
        return {"ok": False,
                "summary": (f"{item['summary']} — 브라우저 수행 실패: "
                            f"{type(e).__name__}: {str(e).splitlines()[0][:160]} (대상: {url})"),
                "evidence": [], "reclaimed": 0.0, "mode": "browser"}


# ── Flow 기록용 증빙 한 줄 ────────────────────────────────

def evidence_note(result: dict) -> str:
    """예: "증빙 2건: data/evidence/.../step1.png, ..." 또는 "증빙 없음 — 시뮬레이션"."""
    evidence = result.get("evidence") or []
    if not evidence:
        return ("증빙 없음 — 시뮬레이션" if result.get("mode") == "simulated"
                else "증빙 없음")
    from pathlib import Path
    paths = ", ".join(_rel(Path(e)) for e in evidence)
    return f"증빙 {len(evidence)}건: {paths}"
