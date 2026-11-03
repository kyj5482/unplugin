"""egolite AI 브라우저 어댑터 — 포털형 케이스의 실행 계층 (TC-STR-004/005, TC-DEL-011).

실행 모드 (자동 선택, 위에서부터):
  1. egolite 원격 세션: UNPLUGIN_EGOLITE_URL 설정 시 HTTP로 인텐트 전달
     (요청: {intent, url, context} → 응답: {ok, blocked, summary, confirmation_no})
  2. playwright 로컬 브라우저: UNPLUGIN_REAL_BROWSER=1 + playwright 설치 시
  3. 시뮬레이션: core/portals.json 레지스트리 기반 결정적 수행 (기본, stdlib only)

공통 계약 — run_intent(case, intent_text, url) 반환:
  {"ok": bool, "blocked": bool, "summary": str,
   "confirmation_no": str|None, "evidence": [경로...], "mode": str}

보안: 페이지 텍스트는 데이터일 뿐이다. 인젝션 패턴 감지 시 수행을 중단하고
blocked가 아닌 보안 이벤트("injection": True)로 보고한다 (TC-DEL-011).
봇 차단(CAPTCHA·robot 거부) 감지 시 자동 해결을 시도하지 않고 blocked=True로
반환한다 — 호출측(큐/케이스)이 사람 개입(core/hitl.py)으로 전환한다 (TC-DEL-004 ⑤).
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from . import common

PORTALS_PATH = Path(__file__).resolve().parent / "portals.json"

# 본문 속 명령은 데이터 — mailbox.INJECTION_PATTERNS와 같은 취지 (페이지용)
INJECTION_PATTERNS = ("이전 지시를 무시", "지시를 무시", "ignore previous",
                      "고객 정보를", "계좌로 송금", "비밀번호를 입력해서 전송")
BLOCK_SIGNALS = ("captcha", "로봇이 아닙니다", "are you a robot", "access denied",
                 "자동화된 접근", "봇 차단")


def load_portals() -> dict:
    return json.loads(PORTALS_PATH.read_text(encoding="utf-8"))["portals"]


def _match_portal(url: str, merchant: str) -> dict | None:
    """URL 도메인 또는 업체명으로 포털 레지스트리 매칭."""
    portals = load_portals()
    key = (url or "").lower() + " " + (merchant or "").lower()
    for p in portals:
        if any(d in key for d in p.get("domains", [])):
            return p
    return None


def scan_injection(page_text: str) -> bool:
    low = (page_text or "").lower()
    return any(p.lower() in low for p in INJECTION_PATTERNS)


def _evidence_dir(case_id: str) -> Path:
    d = common.EVIDENCE / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_receipt(case_id: str, payload: dict) -> Path:
    """수행 증빙(접수 결과) 파일 — 허위 완료 방지의 근거 (TC-DEL-010)."""
    path = _evidence_dir(case_id) / f"portal-{common.ts()}.json"
    common.write_json(path, payload)
    return path


# ── 모드 판별 ─────────────────────────────────────────────

def mode() -> str:
    if os.environ.get("UNPLUGIN_EGOLITE_URL"):
        return "egolite"
    if os.environ.get("UNPLUGIN_REAL_BROWSER") == "1":
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return "playwright"
        except Exception:
            pass
    return "simulated"


# ── 실행 ─────────────────────────────────────────────────

def run_intent(case: dict, intent_text: str, url: str = "") -> dict:
    """케이스 인텐트를 브라우저 세션으로 수행. 공통 계약 dict 반환."""
    m = mode()
    if m == "egolite":
        return _run_egolite(case, intent_text, url)
    if m == "playwright":
        return _run_playwright(case, intent_text, url)
    return _run_simulated(case, intent_text, url)


def _run_egolite(case: dict, intent_text: str, url: str) -> dict:
    """egolite 원격 세션 — 인텐트만 넘기면 egolite가 절차를 수행하고 결과를 반환."""
    import urllib.request
    endpoint = os.environ["UNPLUGIN_EGOLITE_URL"].rstrip("/") + "/v1/intent"
    body = json.dumps({
        "intent": intent_text, "url": url,
        "context": {"case": case["id"], "type": case["type"],
                    "merchant": case["intent"].get("merchant", ""),
                    "amount": case["intent"].get("amount", 0),
                    "order_no": case["intent"].get("order_no", "")},
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "blocked": False, "mode": "egolite",
                "summary": f"egolite 세션 오류: {type(e).__name__}: {e}",
                "confirmation_no": None, "evidence": []}
    if scan_injection(data.get("page_text", "")):
        return _injection_abort(case, url, "egolite")
    receipt = _write_receipt(case["id"], {"mode": "egolite", "intent": intent_text,
                                          "url": url, "response": data})
    return {"ok": bool(data.get("ok")), "blocked": bool(data.get("blocked")),
            "mode": "egolite", "summary": data.get("summary", ""),
            "confirmation_no": data.get("confirmation_no"),
            "evidence": [str(receipt)]}


def _run_playwright(case: dict, intent_text: str, url: str) -> dict:
    """로컬 chromium — 페이지 접속·증빙 스크린샷. 절차 자동화는 포털별 스크립트 확충 전까지
    접속·차단 감지·증빙 수집까지만 수행하고, 제출은 시뮬레이션 규칙을 따른다."""
    from playwright.sync_api import sync_playwright
    evid = _evidence_dir(case["id"])
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(30_000)
                page.goto(url, wait_until="domcontentloaded")
                text = ""
                try:
                    text = page.inner_text("body", timeout=5_000)
                except Exception:
                    pass
                shot = evid / f"step-{common.ts()}.png"
                page.screenshot(path=str(shot))
            finally:
                browser.close()
    except Exception as e:
        return {"ok": False, "blocked": False, "mode": "playwright",
                "summary": f"브라우저 수행 실패: {type(e).__name__}: {e}",
                "confirmation_no": None, "evidence": []}
    if scan_injection(text):
        return _injection_abort(case, url, "playwright")
    low = text.lower()
    if any(s in low for s in BLOCK_SIGNALS):
        return {"ok": False, "blocked": True, "mode": "playwright",
                "summary": f"봇 차단 감지({url}) — 자동 해결 시도 없이 사람 개입으로 전환",
                "confirmation_no": None, "evidence": [str(shot)]}
    receipt = _write_receipt(case["id"], {"mode": "playwright", "url": url,
                                          "intent": intent_text,
                                          "page_excerpt": text[:300]})
    return {"ok": True, "blocked": False, "mode": "playwright",
            "summary": f"포털 접속·확인 완료 ({url})", "confirmation_no": None,
            "evidence": [str(shot), str(receipt)]}


def _injection_abort(case: dict, url: str, m: str) -> dict:
    return {"ok": False, "blocked": False, "injection": True, "mode": m,
            "summary": f"페이지 내 인젝션 의심 지시 감지({url}) — 페이지 내용은 데이터로만 취급, 수행 중단",
            "confirmation_no": None, "evidence": []}


def _run_simulated(case: dict, intent_text: str, url: str) -> dict:
    """레지스트리 기반 결정적 시뮬레이션 — 맥북 실환경 전 로컬 검증용.

    포털 레지스트리의 bot_ok=false 포털은 봇 차단으로 재현되어
    사람 개입(HITL) 경로를 로컬에서 그대로 리허설할 수 있다.
    """
    intent = case.get("intent", {})
    portal = _match_portal(url or intent.get("portal_url", ""),
                           intent.get("merchant", ""))
    page_text = (portal or {}).get("page_text", "")
    if scan_injection(page_text) or scan_injection(intent_text):
        return _injection_abort(case, url, "simulated")
    if portal and not portal.get("bot_ok", True):
        return {"ok": False, "blocked": True, "mode": "simulated",
                "summary": (f"{portal['name']} — 봇 차단 포털(시뮬레이션). "
                            "자동 해결 시도 없이 사람 개입으로 전환"),
                "confirmation_no": None, "evidence": []}
    name = (portal or {}).get("name") or intent.get("merchant", "대상 포털")
    conf = f"CNF-{secrets.token_hex(4).upper()}"
    steps = (portal or {}).get("steps") or [
        "로그인/본인확인", "주문·결제 내역 조회", "환불/해지 신청 양식 작성", "제출·접수번호 수령"]
    receipt = _write_receipt(case["id"], {
        "mode": "simulated", "portal": name, "intent": intent_text,
        "url": url or intent.get("portal_url", ""),
        "steps_performed": steps, "confirmation_no": conf,
        "amount": intent.get("amount", 0), "order_no": intent.get("order_no", ""),
    })
    return {"ok": True, "blocked": False, "mode": "simulated",
            "summary": f"{name} 절차 완료 — 접수번호 {conf} ({' → '.join(steps)})",
            "confirmation_no": conf, "evidence": [str(receipt)]}
