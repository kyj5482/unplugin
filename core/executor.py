"""실행기 — 큐 active 아이템의 수행 계층 (TC-DEL-001~004, 010, 011).

실행 경로:
  ① executor "browser" 플러그인 + 실브라우저 가능 → playwright/egolite 실수행
  ② executor "browser" 플러그인 (로컬) → 업무군별 결정적 시뮬레이션:
       장보기(카트·예산·영수증) / 예약(마감 시 대안 묶음 질문) /
       탐색(추천1+대안2 요약) / 그 외(egolite 포털 시뮬레이션)
  ③ 그 외(auto·call·플러그인 없음) → v0 단순 시뮬레이션 (기존 동작 유지)

반환 계약 (run):
  {"ok", "summary", "evidence", "reclaimed", "mode"}
  + 선택: "blocked"(봇 차단 → HITL), "injection"(보안 이벤트),
          "ask"+"alternatives"(고객 확인 1회 묶음), "partial"(중간 결과)

증빙 원칙 (TC-DEL-010): 주문·예약·접수처럼 외부 거래가 발생하는 수행
(browser 계열)은 증빙 파일(영수증·접수번호) 없이는 완료로 처리되지 않는다.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote_plus

from . import classify, common, egolite

DEFAULT_ENTRYPOINTS = {
    "price-compare": "https://search.danawa.com/dsearch.php?query={query}",
}
FALLBACK_SEARCH = "https://duckduckgo.com/?q={query}"
BROWSER_TIMEOUT_MS = 30_000

# 업무군 분류 (플러그인 id 기준)
CART_PLUGINS = {"grocery-recurring", "kids-supplies-reorder", "pet-supplies-reorder",
                "grocery-fresh-sub", "supplement-reorder", "gift-shopping",
                "flower-cake-order"}
RESEARCH_PLUGINS = {"price-compare", "product-research", "local-research",
                    "weekend-outing-research", "used-buy-search", "real-estate-scan"}

# 장보기 시뮬레이션 카탈로그 (로컬 리허설용 — 실사이트 전 검증)
_SHOP_CATALOG = [
    {"name": "생수 2L 12병", "price": 8900}, {"name": "화장지 30롤", "price": 15900},
    {"name": "세제 리필", "price": 7900}, {"name": "기저귀 1박스", "price": 32900},
    {"name": "분유 800g", "price": 24900}, {"name": "사료 7kg", "price": 29900},
    {"name": "유산균 60포", "price": 19900}, {"name": "물티슈 10팩", "price": 9900},
]

_REQUEST_SUFFIX = re.compile(
    r"\s*(최저가\s*)?(찾아\s*줘|찾아줘|찾기|알아봐\s*줘|알려\s*줘|알려줘|비교해\s*줘|비교해줘|"
    r"주문해\s*줘|주문해줘|예약해\s*줘|예약해줘|해\s*줘|해줘|부탁해요?|주세요)\s*$")
_URL_RE = re.compile(r"url:\s*(\S+)", re.IGNORECASE)


# ── 디스패치 ─────────────────────────────────────────────

def run(item: dict, profile: dict) -> dict:
    plugin = _plugin_of(item)
    if plugin and plugin.get("executor") == "browser":
        if _real_browser_ready():
            return _run_browser(item, plugin, profile)
        pid = plugin.get("id", "")
        if pid in CART_PLUGINS:
            return _sim_cart(item, plugin, profile)
        if pid in RESEARCH_PLUGINS:
            return _sim_research(item, plugin)
        if pid.endswith("-booking") or pid == "waiting-queue":
            return _sim_booking(item, plugin)
        return _sim_portal(item, plugin)
    return _run_simulated(item, plugin)


def _plugin_of(item: dict) -> dict | None:
    kind = item.get("kind", "") or ""
    if not kind.startswith("plugin:"):
        return None
    pid = kind.split(":", 1)[1]
    for pl in classify.load_catalog():
        if pl.get("id") == pid:
            return pl
    return None


def requires_evidence(item: dict) -> bool:
    """외부 거래가 발생하는 수행인지 — 증빙 없이는 완료 불가 (TC-DEL-010)."""
    plugin = _plugin_of(item)
    return bool(plugin and plugin.get("executor") == "browser") \
        or (item.get("kind", "") or "").startswith("case:")


def _real_browser_ready() -> bool:
    if os.environ.get("UNPLUGIN_EGOLITE_URL"):
        return True
    if os.environ.get("UNPLUGIN_REAL_BROWSER") != "1":
        return False
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


def _reclaimed(item: dict, plugin: dict | None) -> float:
    return float(item.get("est_hours")
                 or (plugin or {}).get("est_hours_per_week") or 0.5)


def _text_of(item: dict) -> str:
    return f"{item.get('summary', '')}\n{item.get('body', '')}"


def _receipt(item: dict, payload: dict, name: str) -> str:
    path = common.EVIDENCE / item["id"] / f"{name}-{common.ts()}.json"
    common.write_json(path, payload)
    return str(path)


# ── 시뮬레이션: 일반 (기존 v0 동작 — auto/call/플러그인 없음) ──

def _run_simulated(item: dict, plugin: dict | None) -> dict:
    return {
        "ok": True,
        "summary": f"{item['summary']} 처리 완료 (v0 시뮬레이션 — 증빙 없음)",
        "evidence": [],
        "reclaimed": _reclaimed(item, plugin),
        "mode": "simulated",
    }


# ── 시뮬레이션: 장보기 카트 (TC-DEL-001) ─────────────────

def _sim_cart(item: dict, plugin: dict, profile: dict) -> dict:
    """품목 매칭 → 예산 내 장바구니 구성 → 영수증 증빙. 결제는 큐 승인 게이트 몫."""
    text = _text_of(item)
    budget = item.get("amount") or profile.get("approval_limit") or 30000
    cart = [p for p in _SHOP_CATALOG
            if any(w and w in text for w in p["name"].split()[:1])]
    if not cart:
        cart = [_SHOP_CATALOG[0]]
    picked, total = [], 0
    for p in cart:
        if total + p["price"] <= budget:
            picked.append(p)
            total += p["price"]
    if not picked:
        return {"ok": False, "mode": "sim-cart", "evidence": [], "reclaimed": 0.0,
                "summary": (f"{item['summary']} — 예산 {budget:,}원 안에 담을 수 있는 "
                            "품목이 없어 중단 (예산 조정 필요)")}
    receipt = _receipt(item, {
        "type": "order-receipt", "items": picked, "total": total,
        "budget": budget, "order_no": f"ORD-{common.ts()}",
    }, "receipt")
    names = ", ".join(p["name"] for p in picked)
    return {"ok": True, "mode": "sim-cart", "evidence": [receipt],
            "reclaimed": _reclaimed(item, plugin),
            "summary": (f"{item['summary']} — 장바구니 {len(picked)}개 구성 "
                        f"(합계 {total:,}원 / 예산 {budget:,}원 이내): {names} "
                        f"/ 주문 확정·영수증 증빙 기록")}


# ── 시뮬레이션: 예약 (TC-DEL-002 — 마감 시 대안 묶음 1회 질문) ──

def _sim_booking(item: dict, plugin: dict) -> dict:
    text = _text_of(item)
    if item.get("alt_choice"):
        chosen = item["alt_choice"]
        receipt = _receipt(item, {"type": "booking-confirm", "slot": chosen,
                                  "booking_no": f"BK-{common.ts()}"}, "booking")
        return {"ok": True, "mode": "sim-booking", "evidence": [receipt],
                "reclaimed": _reclaimed(item, plugin),
                "summary": f"{item['summary']} — 고객이 고른 대안 \"{chosen}\"으로 예약 확정 (예약번호 증빙 기록)"}
    if "마감" in text or "slot_full" in text:
        alts = ["같은 날 저녁 8시", "다음날 같은 시간", "인근 대체 업소 같은 시간"]
        return {"ok": False, "ask": True, "alternatives": alts, "mode": "sim-booking",
                "evidence": [], "reclaimed": 0.0, "partial": alts,
                "summary": f"{item['summary']} — 희망 시간대 마감. 대안 {len(alts)}개를 한 번에 정리해 고객 확인 요청"}
    receipt = _receipt(item, {"type": "booking-confirm", "slot": "희망 시간대",
                              "booking_no": f"BK-{common.ts()}"}, "booking")
    return {"ok": True, "mode": "sim-booking", "evidence": [receipt],
            "reclaimed": _reclaimed(item, plugin),
            "summary": f"{item['summary']} — 희망 시간대로 예약 확정 (예약번호 증빙 기록)"}


# ── 시뮬레이션: 탐색 (TC-DEL-003 — 추천1+대안2 요약, 링크≤3) ──

def _sim_research(item: dict, plugin: dict) -> dict:
    q = _query_of(item)
    cands = [
        {"rank": "추천", "name": f"{q} — 1순위 후보", "price": "289,000원",
         "why": "리뷰 평점·가격·보증 조건의 균형이 가장 좋음", "link": "https://shop.example/a"},
        {"rank": "대안 1", "name": f"{q} — 가성비 후보", "price": "219,000원",
         "why": "기능은 유사하나 마감 품질 리뷰가 갈림", "link": "https://shop.example/b"},
        {"rank": "대안 2", "name": f"{q} — 상위 성능 후보", "price": "349,000원",
         "why": "성능 최상, 예산 초과 시 제외", "link": "https://shop.example/c"},
    ]
    lines = [f"[{c['rank']}] {c['name']} · {c['price']} — {c['why']} ({c['link']})"
             for c in cands]
    doc = _receipt(item, {"type": "research-summary", "query": q, "candidates": cands},
                   "research")
    return {"ok": True, "mode": "sim-research", "evidence": [doc],
            "reclaimed": _reclaimed(item, plugin), "partial": cands,
            "summary": f"{item['summary']} — 탐색 요약: " + " / ".join(lines)}


# ── 시뮬레이션: 일반 포털 (egolite 어댑터 경유 — 차단/인젝션 재현) ──

def _sim_portal(item: dict, plugin: dict) -> dict:
    pseudo_case = {"id": item["id"], "type": plugin.get("id", "portal"),
                   "intent": {"merchant": item.get("summary", ""),
                              "portal_url": _entry_url(item, plugin),
                              "amount": item.get("amount", 0)}}
    r = egolite.run_intent(pseudo_case, item.get("summary", ""),
                           _entry_url(item, plugin))
    r["reclaimed"] = _reclaimed(item, plugin) if r.get("ok") else 0.0
    r["summary"] = f"{item['summary']} — {r['summary']}"
    return r


# ── 실브라우저 (playwright — 접속·증빙 PoC) ────────────────

def _query_of(item: dict) -> str:
    q = (item.get("summary") or "").strip()
    q = re.sub(r"^(fwd|re):\s*", "", q, flags=re.IGNORECASE)
    prev = None
    while prev != q:
        prev = q
        q = _REQUEST_SUFFIX.sub("", q).strip()
    return q or (item.get("summary") or "").strip()


def _entry_url(item: dict, plugin: dict) -> str:
    m = _URL_RE.search(_text_of(item))
    if m:
        return m.group(1)
    query = quote_plus(_query_of(item))
    tpl = DEFAULT_ENTRYPOINTS.get(plugin.get("id"), FALLBACK_SEARCH)
    return tpl.format(query=query)


def _rel(path) -> str:
    try:
        return str(path.relative_to(common.ROOT))
    except ValueError:
        return str(path)


def _run_browser(item: dict, plugin: dict, profile: dict) -> dict:
    """실수행 — egolite 세션 우선, 아니면 playwright 접속·증빙."""
    url = _entry_url(item, plugin)
    pseudo_case = {"id": item["id"], "type": plugin.get("id", "portal"),
                   "intent": {"merchant": item.get("summary", ""),
                              "portal_url": url, "amount": item.get("amount", 0)}}
    r = egolite.run_intent(pseudo_case, item.get("summary", ""), url)
    r["reclaimed"] = _reclaimed(item, plugin) if r.get("ok") else 0.0
    r["summary"] = f"{item['summary']} — {r['summary']}"
    return r


# ── Flow 기록용 증빙 한 줄 ────────────────────────────────

def evidence_note(result: dict) -> str:
    evidence = result.get("evidence") or []
    if not evidence:
        return ("증빙 없음 — 시뮬레이션" if result.get("mode") == "simulated"
                else "증빙 없음")
    from pathlib import Path
    paths = ", ".join(_rel(Path(e)) for e in evidence)
    return f"증빙 {len(evidence)}건: {paths}"
