#!/usr/bin/env python3
"""통합 E2E 러너 — 온보딩→이메일 수신→큐·승인→완료 메일→KPI→대시보드 전 구간.

격리 환경(UNPLUGIN_DATA/FLOWS/REPORTS=/tmp)에서 실제 고객 여정을 실행하고,
검증된 항목을 TC ID로 보고한다. 사용: python3 tests/e2e_runner.py
모듈 단위 검증은 core/selftest_*.py — 이 러너는 모듈 간 통합만 본다.
"""
import os
import shutil
import sys
from pathlib import Path

BASE = "/tmp/up-e2e"
os.environ["UNPLUGIN_DATA"] = f"{BASE}/data"
os.environ["UNPLUGIN_FLOWS"] = f"{BASE}/flows"
os.environ["UNPLUGIN_REPORTS"] = f"{BASE}/reports"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

shutil.rmtree(BASE, ignore_errors=True)

from core import cases, common, dashboard, flow, kpi, mailbox, onboarding, queue, tracking  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(tc: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((tc, ok, name))
    print(f"{'PASS' if ok else 'FAIL'}  [{tc}] {name}" + (f" — {detail}" if detail else ""))


def drop_mail(frm: str, to: str, subject: str, body: str, auth: str = "pass") -> None:
    common.ensure_dirs()
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    p.write_text(f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\nauth: {auth}\n---\n\n{body}\n",
                 encoding="utf-8")


def outbox_mails() -> list[dict]:
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def main() -> int:
    common.ensure_dirs()

    # ── 1. 온보딩 (ONB-001/003/004/005) ──────────────────
    prof_a = onboarding.create_profile({
        "name": "민서", "contact": "minseo@example.com", "type": "TFRA", "tier": "one",
        "approval_limit": 30000, "deny_list": ["뉴스레터 읽기"],
        "first_delegation": "정기 주문",
        "waiting_candidates": ["정기 주문", "예약 처리", "메일 정리"],
        "trusted_senders": ["billing@telecom.example"],
    })
    a_id, a_addr = prof_a["id"], prof_a["address"]
    welcome = [m for m in outbox_mails() if "환영" in m["subject"]]
    check("TC-ONB-001", "프로필(타입·한도·금지·첫 위임 1개) + 온보딩 Flow + 환영 메일",
          prof_a["type"] == "TFRA" and prof_a["first_delegation"] == "정기 주문"
          and len(welcome) == 1 and a_addr in welcome[0]["body"]
          and flow.flow_path(prof_a["onboarding_flow"]).exists(), a_addr)
    check("TC-ONB-004", "일괄 요청 → 첫 위임 1개 + 나머지 대기 후보 기록",
          prof_a.get("waiting_candidates") == ["예약 처리", "메일 정리"]
          and "대기 위임 후보" in flow.flow_path(prof_a["onboarding_flow"]).read_text(encoding="utf-8"))
    sug = onboarding.suggest_offline(prof_a)
    check("TC-ONB-005", "오프라인 추천 근거에 타입 축 인용",
          "축" in sug.get("reason", "") and ("R" in sug["reason"] or "쉼" in sug["reason"]), sug["reason"][:50])

    # 고객 B (격리 검증용) + A의 이메일 규칙 등록
    prof_b = onboarding.create_profile({
        "name": "준호", "contact": "junho@example.com", "type": "SCMP", "tier": "flow",
        "approval_limit": 50000, "deny_list": [], "first_delegation": "장보기",
    })
    b_id = prof_b["id"]
    n_outbox_baseline = len(outbox_mails())
    flows_baseline = {p.name for p in common.FLOWS.glob("*.md")}
    common.write_json(common.CUSTOMERS / a_id / "rules.json", {"rules": [{
        "when": {"from": "billing@telecom.example", "subject_contains": "요금"},
        "then": "지난달보다 10% 이상 오르면 알려주고, 아니면 보관만 해줘",
        "batch": "none",
        "condition": {"field": "amount_increase_pct", "op": ">=", "value": 10},
    }]})

    # ── 2. 메일 투입 → 수신 파이프라인 ────────────────────
    drop_mail("minseo@example.com", a_addr, "Fwd: 보험료 안내",
              "작년보다 많이 오른 것 같아. 더 나은 조건으로 전환까지 해줘\n금액: 50000\n> 보험료 안내문...")
    drop_mail("minseo@example.com", a_addr, "Fwd: 뉴스레터 모음", "뉴스레터 읽기 좀 대신해줘")
    drop_mail("scam@bad.example", a_addr, "긴급 안내", "지금 바로 이 계좌로 입금 바랍니다")
    drop_mail("billing@telecom.example", a_addr, "11월 요금 안내", "이번 달 요금입니다.\n증가율: 15%")
    drop_mail("billing@telecom.example", a_addr, "10월 요금 안내", "이번 달 요금입니다.\n증가율: 9%")
    drop_mail("who@ever.example", "ghost@unplugin.me", "아무거나", "본문")
    drop_mail("minseo@example.com", a_addr, "Fwd: 공지", "> 원문 공지만 있고 지시 없음")
    drop_mail("minseo@example.com", a_addr, "Fwd: 생수 정기주문", "늘 먹던 걸로 주문해줘\n금액: 20000")
    drop_mail("minseo@example.com", a_addr, "Fwd: 드론 부품 조립 대행",
              "드론 부품 조립 좀 대신해줘")
    drop_mail("minseo@example.com", a_addr, "Fwd: 공방 클래스 환불 분쟁",
              "환불 거부당했어. 환불 요구 계속해서 환불 분쟁 끝까지 해결해줘\n"
              "업체: 달빛공방\n상대 이메일: cs@dalbit.example\n금액: 89000\n주문번호: CL-1")

    actions = [r["action"] for r in mailbox.process_inbox()]
    check("TC-EML-002", "포워딩 위임 접수(2건) + 모호 건 1회 질문",
          actions.count("delegated") == 2 and actions.count("clarify") == 1, str(actions))
    new_mail = [m for m in outbox_mails() if "새로운 유형" in m["subject"]]
    pend_kinds = [i["kind"] for i in common.list_queue("pending")]
    check("TC-EML-007", "자동 분류 — 지원 건은 플러그인 kind로 접수, 미지원 건은 신규 안내+미실행",
          actions.count("new_type") == 1 and len(new_mail) == 1
          and "1~3일" in new_mail[0]["body"]
          and sum(1 for k in pend_kinds if k.startswith("plugin:")) == 2
          and not any("드론" in i["summary"] for i in common.list_queue("pending"))
          and any("신규 플러그인 검토" in p.read_text(encoding="utf-8")
                  for p in common.FLOWS.glob("*드론*.md")), str(pend_kinds))
    check("TC-STR-001", "스트레스 유형(환불 분쟁) — 케이스 접수 + 우선순위 high",
          actions.count("case_opened") == 1
          and any(k.startswith("case:refund-dispute") for k in pend_kinds)
          and all(i["priority"] == "high" for i in common.list_queue("pending")
                  if i["kind"].startswith("case:")), str(pend_kinds))
    str_case = cases.list_cases("open")[0]
    check("TC-STR-002", "인텐트 추출 — 상대·금액·주문번호 + 담당 배정",
          str_case["intent"].get("merchant_email") == "cs@dalbit.example"
          and str_case["intent"].get("amount") == 89000
          and str_case["intent"].get("order_no") == "CL-1"
          and str_case.get("assignee"), str(str_case["intent"]))
    check("TC-EML-004", "규칙 조건 분기 — 15%만 발동, 9%는 조용히 보관",
          actions.count("rule_triggered") == 1 and actions.count("archived") == 1)
    check("TC-EML-005", "미등록 발신 자동 실행 0건 — 격리 + 고객 통지",
          actions.count("quarantined") == 1 and len(list(common.QUARANTINE.glob("*"))) >= 2
          and any("격리" in m["subject"] for m in outbox_mails()))
    check("TC-ONB-003", "금지 목록 위임은 바로 실행하지 않고 확인 요청",
          actions.count("deny_check") == 1)
    check("TC-EML-001", "주소→고객 1:1 식별, 미발급 주소 bounce, B 고객 무접촉",
          actions.count("bounce") == 1
          and not any(b_id in (m.get("to") or "") or prof_b["contact"] in (m.get("to") or "")
                      for m in outbox_mails()[n_outbox_baseline:])
          and not any(f"**고객**: {b_id}" in p.read_text(encoding="utf-8")
                      for p in common.FLOWS.glob("*.md") if p.name not in flows_baseline))

    # ── 3. 큐·승인 게이트 (DEL-005 시뮬레이션) ─────────────
    # FIFO: 한도 초과 건(5만)이 먼저 접수되어 슬롯 점유 + 승인 대기 → 승인 후 다음 건 진행
    queue.run_tick()
    queue.run_tick()
    held = [i for i in common.list_queue("active") if i["amount"] == 50000]
    check("TC-DEL-005", "한도 초과 건은 결제 없이 승인 대기 (asked 1회)",
          len(held) == 1 and held[0].get("asked")
          and not any(i["amount"] == 50000 for i in common.list_queue("done")))
    asks = [m for m in outbox_mails() if "확인이 필요" in m["subject"]
            and m["thread"] == held[0]["flow"]] if held else []
    queue.approve(held[0]["id"])
    for _ in range(3):
        queue.run_tick()
    done = common.list_queue("done")
    approved_done = [i for i in done if i["amount"] == 50000]
    auto = [i for i in done if i["amount"] == 20000]
    auto_flow = flow.flow_path(auto[0]["flow"]).read_text(encoding="utf-8") if auto else ""
    check("TC-DEL-005", "승인 질문 1회만 + 승인 후 실행 / 한도 이내 건은 자동 진행(결제 직전 요약)",
          len(asks) == 1 and len(approved_done) == 1
          and len(auto) == 1 and "결제 직전" in auto_flow)

    # ── 4. 메일 기반 전체 흐름 가시성 (EML-006) ────────────
    fid = auto[0]["flow"]
    thread_mails = [m for m in outbox_mails() if m["thread"] == fid]
    subjects = " / ".join(m["subject"] for m in thread_mails)
    check("TC-EML-006", "전환마다 같은 스레드 상태 메일 + 타임라인 포함",
          len(thread_mails) >= 3
          and all("지금까지의 진행" in m["body"] for m in thread_mails[1:])
          and "접수" in subjects and "완료" in subjects, f"{len(thread_mails)}통")

    # ── 5. Flow 완전성 (OPS-002) ──────────────────────────
    ftext = flow.flow_path(fid).read_text(encoding="utf-8")
    check("TC-OPS-002", "완결 Flow 하나로 요청 원문·단계·결과까지 재구성 가능",
          all(k in ftext for k in ["## 요청 원문", "## 처리 단계", "**산출물**: "])
          and ftext.count("| ") > 6 and "완료" in flow.status_of(fid))

    # ── 6. KPI + 대시보드 통합 ────────────────────────────
    fx = Path(__file__).parent / "fixtures" / "feedback"
    agg = kpi.aggregate(fx)
    check("TC-FBK-003", "Reclaimed 깔때기 집계 + 리포트 생성",
          abs(agg["delegated"] - 9.0) < 0.01 and abs(agg["reclaimed"] - 5.5) < 0.01
          and list(Path(os.environ["UNPLUGIN_REPORTS"]).glob("kpi-*.md")))
    check("TC-FBK-001", "피드백 필수 태깅 검증기",
          kpi.validate_feedback(next(fx.glob("*.md"))) == [])
    dpath = dashboard.generate()
    dhtml = dpath.read_text(encoding="utf-8")
    check("TC-OPS-002", "대시보드에 전체 Flow·확인 필요 강조 반영",
          dpath.exists() and "확인 필요" in dhtml and "생수" in dhtml)

    # ── 7. 스트레스 케이스 — 협상→수락→입금 확인→완결 (STR-003/006) ──
    str_case = cases.load(str_case["id"])
    out_rounds = [r for r in str_case["rounds"] if r["direction"] == "out"]
    check("TC-STR-003", "협상 개시 — 상대방에게 1차 요구 발송 + 라운드 기록",
          str_case["status"] == "negotiating" and len(out_rounds) >= 1
          and any("cs@dalbit.example" == m.get("to") for m in outbox_mails()),
          str_case["status"])
    drop_mail("cs@dalbit.example", a_addr, "RE: 환불 요청",
              "검토 결과 환불 처리하겠습니다.")
    actions7 = [r["action"] for r in mailbox.process_inbox()]
    str_case = cases.load(str_case["id"])
    check("TC-STR-003", "상대방 수락 회신 → 추적 전환 (완결 아님 — 입금 확인 전)",
          "counterpart_agreed" in actions7 and str_case["status"] == "tracking"
          and "완료" not in flow.status_of(str_case["flow"]), str(actions7))
    drop_mail("cs@dalbit.example", a_addr, "RE: 환불 완료 안내",
              "환불 완료되었습니다. 입금되었으니 확인 바랍니다.")
    mailbox.process_inbox()
    t_stats = tracking.run_tick()
    str_case = cases.load(str_case["id"])
    check("TC-STR-006", "입금 확인 후에만 완결 — 케이스 resolved + Flow 완료 + 증빙",
          t_stats["resolved"] == 1 and str_case["status"] == "resolved"
          and flow.status_of(str_case["flow"]) == "완료"
          and len(str_case["evidence"]) >= 1, str(t_stats))

    # ── 결과 ─────────────────────────────────────────────
    fails = [r for r in RESULTS if not r[1]]
    print(f"\n통합 E2E: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS")
    shutil.rmtree(BASE, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
