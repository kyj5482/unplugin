"""스트레스 케이스 엔진 셀프테스트 — TC-STR-001~008.

실행: python3 core/selftest_stress.py (격리 /tmp 환경)
커버: 유형 감지·인텐트, 협상 분기(거부/부분/수락/에스컬레이션), egolite 차단·인젝션,
HITL 발행·완료·Takeover, 추적 넛지·에스컬레이션, 에이전트 배정, 데모 100통 무결성.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-stress-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ.pop("UNPLUGIN_REAL_BROWSER", None)
os.environ.pop("UNPLUGIN_EGOLITE_URL", None)
sys.path.insert(0, str(ROOT))

from core import (agents, cases, common, egolite, flow, hitl, mailbox,  # noqa: E402
                  negotiation, queue, stress, tracking)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def setup_customer() -> dict:
    common.ensure_dirs()
    shutil.copytree(ROOT / "data/customers/demo", common.CUSTOMERS / "demo",
                    dirs_exist_ok=True)
    return common.read_json(common.CUSTOMERS / "demo/profile.json")


def drop(frm, to, subject, body, thread=""):
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    head = f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\n"
    if thread:
        head += f"thread: {thread}\n"
    p.write_text(head + "---\n\n" + body + "\n", encoding="utf-8")


def outbox():
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def main() -> int:
    prof = setup_customer()
    addr, contact = prof["address"], prof["contact"]

    # ── TC-STR-001/002: 유형 감지·인텐트 추출 (10개 플레이북 전수) ──
    samples = {
        "refund-dispute": "환불 거부당했어, 환불 분쟁 해결해줘",
        "edu-refund": "학원 환불 받아줘, 수강료 환불 기준대로",
        "subscription-refund": "구독 환불 해줘, 미사용분 환불까지",
        "app-refund": "인앱 결제 환불 신청해줘, 실수 결제야",
        "telecom-dispute": "요금 이의신청 넣어줘, 부당 청구야",
        "delivery-refund": "오배송이야, 반품 환불 접수해줘",
        "reservation-refund": "예약 취소 환불인데 취소 수수료가 과해",
        "warranty-claim": "무상수리 요구해줘, 하자 보상 받아야 해",
        "membership-cancel": "헬스장 환불, 회원권 환불 받아줘",
        "deposit-recovery": "보증금 반환을 계속 미뤄",
    }
    ok_all = all((stress.detect(t) or {}).get("id") == pid for pid, t in samples.items())
    check("STR-001 유형 감지 — 10개 플레이북 전수 정확 분류", ok_all,
          str({pid: (stress.detect(t) or {}).get("id") for pid, t in samples.items()}))
    intent = stress.extract_intent("Fwd: 환불", "업체: 달빛공방\n상대 이메일: cs@a.example\n"
                                               "금액: 89,000\n주문번호: CL-77\nurl: https://x.example")
    check("STR-002 인텐트 — 상대·업체·금액(콤마)·주문번호·URL",
          intent == {"goal": "refund", "merchant_email": "cs@a.example",
                     "merchant": "달빛공방", "amount": 89000, "order_no": "CL-77",
                     "portal_url": "https://x.example"}, str(intent))

    # ── TC-STR-001: 우선순위 — 일반 건보다 스트레스 건 먼저 승격 ──
    f_norm = flow.create_flow("demo", "일반 위임", "위임", "메일함 정리해줘")
    queue.enqueue("demo", "plugin:inbox-cleanup", "메일함 정리", f_norm)
    drop(contact, addr, "Fwd: 공방 환불 분쟁",
         "환불 거부당했어. 환불 요구 계속해서 환불 분쟁 해결해줘\n"
         "상대 이메일: cs@gongbang.example\n금액: 50000\n주문번호: GB-1")
    mailbox.process_inbox()
    queue.run_tick()
    done_kinds = [i["kind"] for i in common.list_queue("done")]
    check("STR-001 우선 처리 — 나중에 온 스트레스 건이 먼저 착수(슬롯 1)",
          any(k.startswith("case:") for k in done_kinds)
          and not any(k.startswith("plugin:") for k in done_kinds), str(done_kinds))
    case = cases.list_cases("open")[0]
    check("STR-007 담당 배정 — negotiator(레나) 배정 + Flow에 표기",
          case["assignee"] == "rena"
          and "cs/rena" in flow.flow_path(case["flow"]).read_text(encoding="utf-8"),
          case["assignee"])

    # ── TC-STR-003: 협상 분기 — 거부 라운드 사다리 → 한도 초과 에스컬레이션 제안 ──
    pb = cases.playbook_of(case)
    for _ in range(pb["max_rounds"] + 1):
        drop("cs@gongbang.example", addr, "RE: 환불", "규정상 환불 불가합니다.",
             thread=case["flow"])
        mailbox.process_inbox()
    case = cases.load(case["id"])
    rounds_out = sum(1 for r in case["rounds"] if r["direction"] == "out")
    check("STR-003 거부 반복 → 라운드 사다리 (최대 라운드 도달)",
          rounds_out == pb["max_rounds"], f"out={rounds_out}/{pb['max_rounds']}")
    check("STR-003 최대 라운드 초과 → 임의 진행 없이 고객 에스컬레이션 제안",
          case["status"] == "awaiting_customer"
          and any("에스컬레이션" in m["body"] for m in outbox()), case["status"])
    # 고객이 에스컬레이션 선택 → HITL로 전환
    drop(contact, addr, "RE: 확인", "3", thread=case["flow"])
    mailbox.process_inbox()
    case = cases.load(case["id"])
    check("STR-003 고객 '에스컬레이션' → 분쟁조정 핸드오프 발행",
          case["status"] == "handoff" and len(hitl.list_open()) == 1, case["status"])
    ho = hitl.list_open()[0]
    hitl.complete(ho["id"], "소비자원 1372 접수 완료", "1372-001")
    case = cases.load(case["id"])
    check("STR-005 완료 보고 → 케이스 자동 재개(추적)",
          case["status"] == "tracking", case["status"])

    # ── 부분 제안 분기 ──
    f2 = flow.create_flow("demo", "부분 제안 케이스", "위임", "환불 분쟁")
    pb2 = stress.playbook("refund-dispute")
    c2 = cases.create("demo", f2, pb2, {"goal": "refund", "amount": 100000,
                                        "merchant_email": "cs@p.example"}, "환불 분쟁")
    negotiation.start(c2)
    r = negotiation.handle_reply(c2, {"body": "저희가 50% 환불만 가능합니다.", "path": ""})
    check("STR-003 부분 제안(50%) → 자동 수락 없이 고객 1회 질문",
          r == "partial_offer" and cases.load(c2["id"])["status"] == "awaiting_customer", r)
    c3 = cases.create("demo", f2, pb2, {"goal": "refund", "amount": 100000,
                                        "merchant_email": "cs@p2.example"}, "환불 분쟁")
    negotiation.start(c3)
    r = negotiation.handle_reply(c3, {"body": "95,000원 환불 처리 가능합니다.", "path": ""})
    check("STR-003 부분 제안(95%) → 요구액의 90% 이상이라 수락·추적 전환",
          r == "agreed" and cases.load(c3["id"])["status"] == "tracking", r)

    # ── TC-STR-004: egolite — 포털 수행·차단·인젝션 ──
    sim_case = {"id": "eg-1", "type": "delivery-refund",
                "intent": {"merchant": "쿠팡", "amount": 42000, "order_no": "C-1",
                           "portal_url": "https://coupang.com/orders"}}
    r = egolite.run_intent(sim_case, "환불 접수", "https://coupang.com/orders")
    check("STR-004 포털 수행 — ok + 접수번호 + 증빙 파일 생성",
          r["ok"] and r["confirmation_no"] and Path(r["evidence"][0]).exists(), str(r)[:120])
    r = egolite.run_intent({"id": "eg-2", "type": "app-refund",
                            "intent": {"merchant": "구글", "portal_url": "https://play.google.com/x"}},
                           "환불", "https://play.google.com/x")
    check("STR-004 봇 차단 포털 — blocked=True, 자동 해결 시도 없음",
          not r["ok"] and r["blocked"], str(r)[:120])
    r = egolite.run_intent({"id": "eg-3", "type": "x",
                            "intent": {"merchant": "evil", "portal_url": "https://evil.example"}},
                           "환불", "https://evil.example")
    check("STR-004/DEL-011 페이지 인젝션 — 수행 중단 + injection 플래그",
          not r["ok"] and r.get("injection"), str(r)[:120])

    # ── TC-STR-006: 추적 — 기한 초과 넛지 → 한도 초과 에스컬레이션 ──
    f4 = flow.create_flow("demo", "추적 케이스", "위임", "환불")
    c4 = cases.create("demo", f4, pb2, {"goal": "refund", "amount": 70000,
                                        "merchant_email": "cs@slow.example"}, "환불")
    tracking.schedule(c4)
    for n in (1, 2):
        c4 = cases.load(c4["id"])
        c4["tracking"]["expected_by"] = common.iso(common.now() - timedelta(days=1))
        cases.save(c4)
        tracking.run_tick()
        c4 = cases.load(c4["id"])
        check(f"STR-006 기한 초과 {n}차 — 상대방 넛지 메일 + 기록",
              c4["tracking"]["nudges"] == n
              and any("처리 확인 요청" in m["subject"] for m in outbox()), str(c4["tracking"]))
    c4["tracking"]["expected_by"] = common.iso(common.now() - timedelta(days=1))
    cases.save(c4)
    tracking.run_tick()
    c4 = cases.load(c4["id"])
    check("STR-006 넛지 한도 초과 — 고객에게 에스컬레이션 선택지 (임의 진행 금지)",
          c4["status"] == "awaiting_customer", c4["status"])

    # ── TC-STR-007: 에이전트 조직 — 로스터·역할·부하 분산 ──
    roles = {a["role"] for a in agents.roster()}
    check("STR-007 로스터 — 5개 역할 전부 존재",
          roles == {"concierge", "resolver", "negotiator", "tracker", "coordinator"},
          str(roles))
    a1 = agents.assign("resolver")
    check("STR-007 배정 — 부하 최소 resolver 선택", a1["role"] == "resolver", str(a1))

    # ── TC-STR-008: 데모 100통 무결성 ──
    idx = json.loads((ROOT / "demo/index.json").read_text(encoding="utf-8"))
    emails = idx["emails"]
    by_type: dict[str, int] = {}
    all_parse = all_detect = True
    for e in emails:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        mail = common.parse_mail(ROOT / "demo" / e["file"])
        if mail["to"] != prof["address"]:
            all_parse = False
        pb_hit = stress.detect(f"{mail['subject']} {mail['body']}")
        if not pb_hit or pb_hit["id"] != e["type"]:
            all_detect = False
    check("STR-008 데모 100통 — 10유형×10통, 포맷·수신 주소 정합",
          idx["count"] == 100 and len(emails) == 100
          and len(by_type) == 10 and all(v == 10 for v in by_type.values())
          and all_parse, str(by_type))
    check("STR-008 데모 100통 — 전부 의도한 플레이북으로 분류", all_detect)

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
