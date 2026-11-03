"""위임 실행 셀프테스트 — TC-DEL-001~004, 006~013.

실행: python3 core/selftest_delegation.py (격리 /tmp 환경)
시뮬레이션 기준 리허설 — 실브라우저(맥북) 실증 시 동일 TC로 재검증한다.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-del-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ.pop("UNPLUGIN_REAL_BROWSER", None)
os.environ.pop("UNPLUGIN_EGOLITE_URL", None)
sys.path.insert(0, str(ROOT))

from core import (common, executor, flow, hitl, mailbox, queue,  # noqa: E402
                  recurring)

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


def main() -> int:
    common.ensure_dirs()
    shutil.copytree(ROOT / "data/customers/demo", common.CUSTOMERS / "demo",
                    dirs_exist_ok=True)
    prof = common.read_json(common.CUSTOMERS / "demo/profile.json")
    prof["tier"] = "life"  # 리허설 편의: 슬롯 4 (보류 건이 슬롯을 점유하므로)
    common.write_json(common.CUSTOMERS / "demo/profile.json", prof)
    addr, contact = prof["address"], prof["contact"]

    # ── DEL-001: 장보기 — 예산 내 카트 + 영수증 증빙 + Flow 기록 ──
    f1 = flow.create_flow("demo", "생수 정기주문", "위임", "늘 먹던 생수 주문")
    i1 = queue.enqueue("demo", "plugin:grocery-recurring", "생수 정기주문", f1)
    queue.run_tick()
    d1 = common.queue_item_path("done", i1)
    ftext = flow.flow_path(f1).read_text(encoding="utf-8")
    check("DEL-001 장보기 — 예산 내 카트·주문 완료·영수증 증빙·Flow 기록",
          d1.exists() and "예산" in ftext and "증빙 1건" in ftext
          and list((common.EVIDENCE / i1).glob("receipt-*.json")), ftext[-200:])

    # ── DEL-002: 예약 마감 → 대안 묶음 1회 질문 → 선택 → 확정 ──
    f2 = flow.create_flow("demo", "토요일 저녁 식당 예약", "위임", "가족 식당 예약")
    i2 = queue.enqueue("demo", "plugin:restaurant-booking",
                       "토요일 저녁 식당 예약", f2, body="희망 시간대 마감")
    queue.run_tick()
    queue.run_tick()  # 재질문 금지 확인용 한 틱 더
    asks = [m for m in outbox() if m["thread"] == f2 and "대안" in m["body"]]
    it2 = common.read_json(common.queue_item_path("active", i2))
    check("DEL-002 마감 → 대안 2~3개 묶음 질문 1회 (반복 핑퐁 없음)",
          len(asks) == 1 and it2.get("asked_alt") and it2.get("hold") == "await_choice",
          f"asks={len(asks)}")
    drop(contact, addr, "RE: 예약", "2", thread=f2)
    mailbox.process_inbox()
    queue.run_tick()
    check("DEL-002 고객 선택 반영 → 대안으로 예약 확정 + 증빙",
          common.queue_item_path("done", i2).exists()
          and "대안" in flow.flow_path(f2).read_text(encoding="utf-8"))

    # ── DEL-003: 탐색 — 추천1+대안2 요약, 링크 3개 이하 ──
    f3 = flow.create_flow("demo", "노이즈캔슬링 헤드폰 최저가 찾아줘", "위임", "탐색")
    i3 = queue.enqueue("demo", "plugin:price-compare",
                       "노이즈캔슬링 헤드폰 최저가 찾아줘", f3)
    queue.run_tick()
    f3text = flow.flow_path(f3).read_text(encoding="utf-8")
    summary_line = next((l for l in f3text.splitlines() if "실행 요약" in l), "")
    check("DEL-003 탐색 — [추천]+[대안 1]+[대안 2]+이유·가격, 링크 ≤3 (자족적 요약)",
          all(k in summary_line for k in ("[추천]", "[대안 1]", "[대안 2]", "원"))
          and summary_line.count("http") <= 3,
          f"links={summary_line.count('http')}")

    # ── DEL-004: 반복 실패 → 중단·통지·대안 / 무한 재시도 금지 ──
    f4 = flow.create_flow("demo", "실패 리허설", "위임", "실패")
    i4 = queue.enqueue("demo", "plugin:price-compare", "실패 리허설", f4)
    orig_run = executor.run
    executor.run = lambda it, p: {"ok": False, "summary": "사이트 장애", "evidence": [],
                                  "reclaimed": 0.0, "mode": "sim"}
    try:
        for _ in range(4):
            queue.run_tick()
    finally:
        executor.run = orig_run
    it4 = common.read_json(common.queue_item_path("active", i4))
    f4text = flow.flow_path(f4).read_text(encoding="utf-8")
    check("DEL-004 2회 실패 → 중단·확인 필요·대안 안내, 이후 재시도 없음(hold)",
          it4.get("fail_count") == 2 and it4.get("hold") == "await_customer"
          and "대안: ①" in f4text and flow.status_of(f4) == "확인 필요",
          f"fail_count={it4.get('fail_count')}, hold={it4.get('hold')}")
    queue.cancel(i4, by_customer=False)  # 슬롯 반납 (리허설 정리)

    # ── DEL-004 ⑤ + STR-005: 봇 차단 → 즉시 사람 개입 (자동 해결 시도 금지) ──
    f5 = flow.create_flow("demo", "차단 포털 작업", "위임", "차단")
    i5 = queue.enqueue("demo", "plugin:form-filling", "양식 작성 제출", f5,
                       body="url: https://play.google.com/forms")
    queue.run_tick()
    it5 = common.read_json(common.queue_item_path("active", i5))
    hos = hitl.list_open()
    check("DEL-004⑤ 봇 차단 — 재시도 없이 즉시 HITL 가이드 + hold",
          it5.get("hold") == "handoff" and len(hos) == 1, str(it5.get("hold")))
    hitl.complete(hos[0]["id"], "직원이 직접 제출 완료", "FRM-99")
    check("DEL-004⑤ 사람 완료 보고 → 사람 증빙으로 완결",
          common.queue_item_path("done", i5).exists()
          and "FRM-99" in flow.flow_path(f5).read_text(encoding="utf-8"))

    # ── DEL-006: 민감정보 평문 기록 금지 + Takeover 안내 ──
    drop(contact, addr, "Fwd: 생수 주문",
         "늘 먹던 걸로 주문해줘. 카드번호 1234-5678-9012-3456 으로 결제하고 비밀번호: abcd1234 야")
    mailbox.process_inbox()
    all_text = ""
    for base in (common.FLOWS, common.OUTBOX, common.CASES, common.QUEUE):
        for p in Path(base).rglob("*"):
            if p.is_file():
                try:
                    all_text += p.read_text(encoding="utf-8")
                except Exception:
                    pass
    check("DEL-006 카드번호·비밀번호 — flow/outbox/큐 어디에도 평문 없음",
          "1234-5678-9012-3456" not in all_text and "abcd1234" not in all_text)
    check("DEL-006 Takeover 안내 메일 발송",
          any("Takeover" in m["body"] for m in outbox()))

    # ── DEL-007: 범위 밖 거절 + 대안 1개 + Flow 기록 ──
    drop(contact, addr, "Fwd: 부탁", "남친 타인 SNS 몰래 확인 좀 해줘")
    drop(contact, addr, "Fwd: 이체", "엄마 계좌 이체해줘, 50만원")
    acts = [r["action"] for r in mailbox.process_inbox()]
    refusals = [m for m in outbox() if "맡아드릴 수 없어요" in m["subject"]]
    check("DEL-007 범위 밖·고위험 2건 — 수행 없이 거절 + 대안 제시 + Flow 기록",
          acts.count("refused") == 2 and len(refusals) == 2
          and all("대신 이런 건 가능해요" in m["body"] for m in refusals), str(acts))

    # ── DEL-008: 진행 상태 조회 ──
    f8 = flow.create_flow("demo", "상태 조회 리허설", "위임", "조회")
    queue.enqueue("demo", "plugin:inbox-cleanup", "상태 조회 리허설", f8)
    drop(contact, addr, "RE: 진행", "지금 어떻게 되고 있어요?", thread=f8)
    mailbox.process_inbox()
    status_mails = [m for m in outbox() if "어떻게 되고 있냐면요" in m["subject"]]
    check("DEL-008 상태 질의 — 현재 단계·예상/대기 정보 응답",
          len(status_mails) == 1 and "지금 상태" in status_mails[0]["body"]
          and "최근 단계" in status_mails[0]["body"], str(len(status_mails)))

    # ── DEL-009: 진행 중 취소 → 중간 결과 반환 ──
    f9 = flow.create_flow("demo", "취소 리허설 탐색", "위임", "탐색 취소")
    i9 = queue.enqueue("demo", "plugin:product-research", "로봇청소기 추천해줘", f9)
    it9p = common.queue_item_path("pending", i9)
    it9 = common.read_json(it9p)
    it9["partial"] = ["후보A 29만", "후보B 32만"]
    common.write_json(it9p, it9)
    drop(contact, addr, "RE: 탐색", "취소할게요", thread=f9)
    mailbox.process_inbox()
    c9 = common.queue_item_path("cancelled", i9)
    check("DEL-009 진행 중 취소 — 안전 중단 + 중간 결과 반환 + 미차감",
          c9.exists() and common.read_json(c9)["charged"] is False
          and any("중간 결과" in m["body"] for m in outbox() if m["thread"] == f9)
          and flow.status_of(f9) == "취소")

    # ── DEL-010: 증빙 없는 완료 보고 → 완결 차단 ──
    f10 = flow.create_flow("demo", "증빙 게이트", "위임", "증빙")
    i10 = queue.enqueue("demo", "plugin:ticket-booking", "콘서트 예매", f10)
    executor.run = lambda it, p: {"ok": True, "summary": "예매 완료(라고 주장)",
                                  "evidence": [], "reclaimed": 0.4, "mode": "sim"}
    try:
        queue.run_tick()
    finally:
        executor.run = orig_run
    it10 = common.read_json(common.queue_item_path("active", i10))
    check("DEL-010 증빙 없는 완료 — done 이동 금지 + 보류 기록",
          it10.get("hold") == "no_evidence"
          and not common.queue_item_path("done", i10).exists()
          and "증빙" in flow.flow_path(f10).read_text(encoding="utf-8"))
    queue.cancel(i10, by_customer=False)  # 슬롯 반납

    # ── DEL-011: 방문 페이지 인젝션 → 중단 + 보안 이벤트 ──
    f11 = flow.create_flow("demo", "인젝션 페이지", "위임", "인젝션")
    i11 = queue.enqueue("demo", "plugin:form-filling", "설문 작성", f11,
                        body="url: https://evil.example/form")
    queue.run_tick()
    it11 = common.read_json(common.queue_item_path("active", i11))
    check("DEL-011 페이지 지시 미추종 — 중단 + Flow 보안 이벤트 + hold",
          it11.get("hold") == "security"
          and "[보안 이벤트]" in flow.flow_path(f11).read_text(encoding="utf-8"))
    queue.cancel(i11, by_customer=False)  # 슬롯 반납

    # ── DEL-012: Takeover 가이드 — 기록 중지 명시 + 재개/재시작 경로 ──
    from core import cases as cases_mod, stress
    f12 = flow.create_flow("demo", "정부24 환급금", "위임", "환급")
    c12 = cases_mod.create("demo", f12, stress.playbook("deposit-recovery"),
                           {"goal": "refund", "merchant": "정부24",
                            "portal_url": "https://gov.kr"}, "환급금 수령")
    i12 = queue.enqueue("demo", "case:deposit-recovery", "환급금 수령", f12,
                        case_id=c12["id"])
    queue.run_tick()
    ho12 = [h for h in hitl.list_open() if h["case"] == c12["id"]]
    guide = (common.HANDOFF / f"{ho12[0]['id']}.md").read_text(encoding="utf-8") if ho12 else ""
    check("DEL-012 Takeover — 기록 중지 구간·재시작 경로 명시 가이드",
          ho12 and ho12[0]["kind"] == "takeover"
          and "기록 중지" in guide and "다시 시작" in guide, str(ho12))
    hitl.complete(ho12[0]["id"], "고객 본인 인증 후 환급 신청 완료", "GOV-1")
    check("DEL-012 입력 완료 후 재개 — 케이스 추적 전환",
          cases_mod.load(c12["id"])["status"] == "tracking")

    # ── DEL-013: 반복 위임 — 회차 자동 실행 + 게이트 + 일시정지 ──
    rec = recurring.register("demo", "매주 생필품 주문", "plugin:grocery-recurring",
                             7, amount=20000, est_hours=1.5)
    n1 = recurring.run_tick()
    n_again = recurring.run_tick()  # next_at 미도래 → 생성 없음
    r1_items = [i for i in common.list_queue("pending") + common.list_queue("active")
                if "1회차" in i["summary"]]
    check("DEL-013 회차 자동 생성 1건 (중복 생성 없음) + Flow 기록",
          n1 == 1 and n_again == 0 and len(r1_items) == 1
          and r1_items[0]["amount"] == 20000, f"n1={n1}, again={n_again}")
    queue.run_tick()
    recurring.set_paused("demo", rec["id"], True)
    items = recurring.list_for("demo")
    items[0]["next_at"] = common.iso()
    recurring._save("demo", items)
    recurring.set_paused("demo", rec["id"], True)
    check("DEL-013 일시정지 — 시점이 되어도 회차 생성 없음",
          recurring.run_tick() == 0)
    check("DEL-013 해지", recurring.remove("demo", rec["id"]) is True)

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
