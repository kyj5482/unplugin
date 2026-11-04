"""시간 배당(측정 v0)·팁 엔진 셀프테스트 — TC-DIV-001~006, TC-TIP-001~003.

피벗(2026-11-04) 기본 모드(팁 회신 + 보고 자동 적립)를 검증한다 —
UNPLUGIN_LEGACY_DELEGATION 없이 실행해야 한다.
실행: python3 core/selftest_dividend.py (격리 /tmp 환경)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-div-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ["UNPLUGIN_REPORTS"] = str(_TMP / "reports")
os.environ.pop("UNPLUGIN_LEGACY_DELEGATION", None)  # 피벗 기본 모드 검증
sys.path.insert(0, str(ROOT))

from core import classify, common, dividend, mailbox, onboarding, tips  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def drop(frm, to, subject, body, thread=""):
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    head = f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\n"
    if thread:
        head += f"thread: {thread}\n"
    p.write_text(head + "---\n\n" + body + "\n", encoding="utf-8")


def outbox():
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def pendings():
    return common.list_queue("pending") + common.list_queue("active")


def main() -> int:
    common.ensure_dirs()
    prof = onboarding.create_profile({
        "name": "배당", "contact": "div@example.com", "type": "SFRA", "tier": "one",
        "approval_limit": 30000, "deny_list": [], "first_delegation": "메일 정리"})
    cid, addr, contact = prof["id"], prof["address"], prof["contact"]
    ppath = common.CUSTOMERS / cid / "profile.json"
    p = common.read_json(ppath)
    p["movement_threshold_minutes"] = 120
    common.write_json(ppath, p)
    n_queue0 = len(pendings())

    # ── TIP-001: 일반 포워딩 업무 → 팁 카드 회신, 대행 접수 0건 ──
    drop(contact, addr, "Fwd: 생수 정기주문", "늘 먹던 생수 주문해줘")
    res = mailbox.process_inbox()
    tip_mails = [m for m in outbox() if "더 좋은 방법" in m["subject"]]
    check("TIP-001 포워딩 업무 → 팁 카드 회신 (대행 큐 미생성)",
          res[0]["action"] == "tip_sent" and len(pendings()) == n_queue0
          and len(tip_mails) == 1, str(res))
    body1 = tip_mails[0]["body"] if tip_mails else ""
    check("TIP-001 팁 카드에 [보고] 한 줄 + 전용주소 + 자동 적립 안내",
          dividend.REPORT_MARKER in body1 and addr in body1
          and "자동" in body1 and "예상 절약" in body1, body1[:200])

    # ── TIP-002: 스트레스 유형 → 고급 팁 (입금 확인까지·에스컬레이션), 케이스 미생성 ──
    drop(contact, addr, "Fwd: 공방 클래스 환불 분쟁",
         "환불 거부당했어. 환불 요구 계속해줘\n업체: 달빛공방\n금액: 89000")
    res2 = mailbox.process_inbox()
    from core import cases
    stress_tip = [m for m in outbox() if "환불" in m["subject"] and "더 좋은 방법" in m["subject"]]
    body2 = stress_tip[-1]["body"] if stress_tip else ""
    check("TIP-002 스트레스 유형 → 고급 팁 (입금 확인·재촉·에스컬레이션 포함, 케이스 0건)",
          res2[0]["action"] == "tip_sent" and not cases.list_cases("open")
          and "입금" in body2 and "재촉" in body2, body2[:200])

    # ── TIP-003: 미매칭 업무 → 범용 팁 + 플레이스홀더 주소 ──
    card = tips.make_tip("즈브흐 장치 작업")
    check("TIP-003 미매칭 → 범용 팁 (보고 한 줄 + 플레이스홀더)",
          card["matched"] is False and tips.PLACEHOLDER_ADDR in card["muze_prompt"]
          and dividend.REPORT_MARKER in card["muze_prompt"], str(card))

    # ── DIV-001: [보고] 마커 적립 — 유형 매칭 기준치 ──
    expected = next(pl for pl in classify.load_catalog()
                    if pl["id"] == "grocery-recurring")
    drop(contact, addr, "[보고] 생수 정기주문", "늘 먹던 생수 정기 주문 처리했어. 장보기 끝.")
    r1 = mailbox.process_inbox()
    led = dividend.load_ledger(cid)
    e1 = led["events"][-1] if led["events"] else {}
    accrual_mails = [m for m in outbox() if "시간 배당 적립" in m["subject"]]
    check("DIV-001 [보고] 마커 → 자동 적립 (유형 매칭·기준치·적립 확인 메일)",
          r1[0]["action"] == "report_accrued" and e1.get("matched") is True
          and e1.get("saved_minutes") == expected["baseline_minutes"]
          and len(accrual_mails) == 1 and "누적 잔고" in accrual_mails[0]["body"],
          str(e1))
    check("DIV-001 수동 입력 경로 없음 — 적립은 메일 수신으로만 (큐·플로우 접수 0건)",
          len(pendings()) == n_queue0)
    total = e1.get("saved_minutes", 0)

    # ── DIV-002: 마커 없는 완료 키워드 휴리스틱 ──
    drop(contact, addr, "숙소 예약 건", "오사카 숙소 예약 끝냈습니다. 완료.")
    r2 = mailbox.process_inbox()
    led = dividend.load_ledger(cid)
    check("DIV-002 마커 없음 + 완료 키워드 → 관대 판정 적립",
          r2[0]["action"] == "report_accrued"
          and led["totals"]["events_count"] == 2, str(r2))
    total = led["totals"]["saved_minutes"]

    # ── DIV-003: 스트레스 유형 보고 — 감정 가중 ──
    drop(contact, addr, "[보고] 공방 환불 분쟁 종결",
         "환불 요구 협상 마쳤고 89,000원 입금 확인 완료")
    mailbox.process_inbox()
    led = dividend.load_ledger(cid)
    e3 = led["events"][-1]
    check("DIV-003 스트레스 유형 보고 — 감정 가중(≥4) + 시간 가중(≥90분)",
          e3["emotion_load"] >= 4 and e3["saved_minutes"] >= 90, str(e3))

    # ── DIV-004: 임계치 도달 → 무브먼트 제안, 같은 구간 중복 없음 ──
    movement = [m for m in outbox() if "무브먼트" in m["subject"]]
    check("DIV-004 임계치(120분) 도달 → 무브먼트 제안 1통 (관계·배움·오감)",
          len(movement) == 1 and all(k in movement[0]["body"]
                                     for k in ("관계", "배움", "오감")),
          f"{len(movement)}통")

    # ── DIV-005: 미매칭 보고 — 기본값 적립 + matched:false 기록 ──
    drop(contact, addr, "[보고] 즈브흐 장치", "즈브흐 장치 건 처리했어")
    mailbox.process_inbox()
    led = dividend.load_ledger(cid)
    e5 = led["events"][-1]
    check("DIV-005 미매칭 보고 — 기본값(30분/감정 2) 적립 + matched:false",
          e5["matched"] is False and e5["saved_minutes"] == dividend.DEFAULT_BASELINE
          and e5["emotion_load"] == dividend.DEFAULT_EMOTION, str(e5))
    movement = [m for m in outbox() if "무브먼트" in m["subject"]]
    check("DIV-004 같은 임계치 구간 — 추가 적립에도 중복 제안 없음",
          len(movement) == 1, f"{len(movement)}통")

    # ── DIV-006: 다음 구간 진입 → 제안 재발송 + 잔고 합계 일관성 ──
    before = led["totals"]["saved_minutes"]
    drop(contact, addr, "[보고] 보증금 반환", "보증금 반환 받아냈어. 입금 확인 완료")
    mailbox.process_inbox()
    led = dividend.load_ledger(cid)
    movement = [m for m in outbox() if "무브먼트" in m["subject"]]
    sum_events = sum(e["saved_minutes"] for e in led["events"])
    check("DIV-006 다음 임계치 구간 → 제안 재발송 + 잔고=이벤트 합",
          len(movement) == 2 and led["totals"]["saved_minutes"] == sum_events
          and led["totals"]["saved_minutes"] > before,
          f"{len(movement)}통, 잔고 {led['totals']['saved_minutes']}")

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
