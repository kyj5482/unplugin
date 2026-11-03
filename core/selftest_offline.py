"""오프라인 전환·피드백·마케팅·운영 셀프테스트 —
TC-OFF-001~004, FBK-002/004, MKT-001~003, OPS-001/005, ONB-002/006.

실행: python3 core/selftest_offline.py (격리 /tmp 환경)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-off-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ["UNPLUGIN_REPORTS"] = str(_TMP / "reports")
sys.path.insert(0, str(ROOT))

from core import (billing, common, directive, flow, kpi, mailbox,  # noqa: E402
                  marketing, onboarding, queue, recommend)

PASS = FAIL = 0
FEEDBACK = _TMP / "feedback"


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


def feedback_file(name: str, **fields) -> Path:
    FEEDBACK.mkdir(parents=True, exist_ok=True)
    lines = ["---"] + [f"{k}: {v}" for k, v in fields.items()] + ["---", ""]
    p = FEEDBACK / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main() -> int:
    common.ensure_dirs()
    shutil.copytree(ROOT / "data/customers/demo", common.CUSTOMERS / "demo",
                    dirs_exist_ok=True)
    prof = common.read_json(common.CUSTOMERS / "demo/profile.json")
    prof["type"] = "SFMP"  # M축(만들기)·P축(함께) — 촉각형 추천 검증용
    common.write_json(common.CUSTOMERS / "demo/profile.json", prof)
    addr, contact = prof["address"], prof["contact"]

    # ── OFF-001: 위임 완료 → 시간 추정 + 근거 있는 추천 1~3개, 체험·배움 우선 ──
    f1 = flow.create_flow("demo", "장보기 위임", "위임", "장보기")
    i1 = queue.enqueue("demo", "plugin:grocery-recurring", "생수 주문", f1,
                       est_hours=2.0)
    queue.run_tick()
    f1text = flow.flow_path(f1).read_text(encoding="utf-8")
    rec_mails = [m for m in outbox() if "화면 밖에서" in m["subject"]]
    check("OFF-001 완료 → 확보 시간 Flow 기록 + 추천 1~3개 발송",
          "오프라인 추천" in f1text and len(rec_mails) == 1, f"{len(rec_mails)}통")
    body1 = rec_mails[0]["body"] if rec_mails else ""
    check("OFF-001 추천 근거 3요소 — 시간·타입 축·이유 (M/P축 우선)",
          "시간" in body1 and "축" in body1 and "M축" in body1.replace("M축", "M축"),
          body1[:150])
    prof1 = common.read_json(common.CUSTOMERS / "demo/profile.json")
    first_titles = set(prof1.get("suggested_history", []))
    check("OFF-001 소비형보다 체험·배움형 우선 — 첫 추천 목록에 소비형 없음",
          first_titles and not ({"야시장 나들이", "문구점 쇼핑 산책"} & first_titles),
          str(first_titles))

    # ── OFF-002: 거절 2회 → 제약 누적 + 동일 추천 재등장 0회 ──
    drop(contact, addr, "RE: 추천", "거절: 집에서 머니까 부담돼요", thread=f1)
    mailbox.process_inbox()
    prof2 = common.read_json(common.CUSTOMERS / "demo/profile.json")
    second_titles = set(prof2.get("suggested_history", [])) - first_titles
    check("OFF-002 거절 1회 — 이동 거리 제약 프로필 누적 + 재추천",
          prof2.get("constraints", {}).get("max_distance_km") == 5
          and second_titles and not (second_titles & first_titles),
          f"constraints={prof2.get('constraints')}, new={second_titles}")
    drop(contact, addr, "RE: 추천", "거절: 혼자 하는 게 좋아요", thread=f1)
    mailbox.process_inbox()
    prof3 = common.read_json(common.CUSTOMERS / "demo/profile.json")
    third_titles = set(prof3.get("suggested_history", [])) - first_titles - second_titles
    check("OFF-002 거절 2회 — 동일 추천 재등장 0회 + 제약 2건 누적",
          not (third_titles & (first_titles | second_titles))
          and len(prof3.get("constraint_labels", [])) >= 2,
          f"labels={prof3.get('constraint_labels')}")

    # ── OFF-003: 수락 → 같은 Flow에서 예약 위임 ──
    drop(contact, addr, "RE: 추천", "수락: 도자기 원데이 클래스", thread=f1)
    mailbox.process_inbox()
    booking = [i for i in common.list_queue("pending") + common.list_queue("active")
               if i["flow"] == f1 and "예약" in i["summary"]]
    f1text = flow.flow_path(f1).read_text(encoding="utf-8")
    check("OFF-003 수락 → 동일 Flow에 위임→추천→예약 연결",
          len(booking) == 1 and "예약 위임으로 전환" in f1text, str(booking))

    # ── OFF-004: 2주 재문진 — 실측 저장 + 추정 대비 차이 핸드오프 ──
    p4 = recommend.resurvey("demo", {
        "screen_before_h": 21, "screen_after_h": 17.5, "offline_realized": "yes",
        "offline_story": "주말에 도자기 클래스 다녀왔어요", "delegation": "장보기",
        "satisfaction": 5, "estimate_h": 2.0}, feedback_dir=FEEDBACK)
    fm_ok = kpi.validate_feedback(p4) == []
    txt4 = p4.read_text(encoding="utf-8")
    resurvey_flows = [f for f in common.FLOWS.glob("*재문진*.md")]
    check("OFF-004 재문진 — 스크린타임 변화·실측 reclaimed 저장 (필수 태깅 합격)",
          fm_ok and "reclaimed_hours: 3.5" in txt4 and "screen_before_h: 21" in txt4,
          txt4[:150])
    check("OFF-004 추정 대비 실측 차이 상품기획 핸드오프",
          resurvey_flows and "cs → product" in resurvey_flows[0].read_text(encoding="utf-8")
          and "estimate_vs_actual: +1.5" in txt4)

    # ── FBK-002: no 케이스 — 원인 자동 분류 + 개선 Flow 핸드오프 ──
    feedback_file("fb-no-1.md", customer="demo", delegation="장보기", satisfaction=4,
                  offline_realized="no", offline_story="시간은 생겼는데 그냥 유튜브 봤어요",
                  delegated_hours=2, reclaimed_hours=0)
    created = kpi.process_unrealized(FEEDBACK)
    cause_flows = [flow.flow_path(f).read_text(encoding="utf-8") for f in created]
    check("FBK-002 원인 분류(동기 부족) + 상품기획 핸드오프 Flow",
          any("동기 부족" in t and "cs → product" in t for t in cause_flows),
          str(created))

    # ── FBK-004: 반복 불만(고객 2명) → 담당 부문 개선 과제 Flow ──
    feedback_file("fb-c1.md", customer="demo", delegation="주문", satisfaction=3,
                  offline_realized="yes", offline_story="좋았어요", delegated_hours=1,
                  reclaimed_hours=1, complaint="승인 요청이 너무 잦음")
    feedback_file("fb-c2.md", customer="minsu", delegation="예약", satisfaction=3,
                  offline_realized="yes", offline_story="괜찮았어요", delegated_hours=1,
                  reclaimed_hours=1, complaint="승인 요청이 너무 잦음")
    made = kpi.weekly_complaints(FEEDBACK)
    check("FBK-004 반복 불만 감지 — IT 개선 과제 Flow 생성",
          len(made) == 1 and made[0]["dept"] == "it" and made[0]["customers"] == 2
          and flow.flow_path(made[0]["flow"]).exists(), str(made))
    feedback_file("fb-c3.md", customer="demo", delegation="주문", satisfaction=3,
                  offline_realized="yes", offline_story="응", delegated_hours=1,
                  reclaimed_hours=1, complaint="단독 불만")
    made2 = kpi.weekly_complaints(FEEDBACK)
    check("FBK-004 1명 불만은 과제 전환 없음 (기존 반복건만)",
          all(m["tag"] != "단독 불만" for m in made2), str(made2))

    # ── MKT-002: 실데이터 없으면 가상 스토리 거부 ──
    empty = _TMP / "empty-feedback"
    empty.mkdir(exist_ok=True)
    r = marketing.write_story(feedback_dir=empty)
    check("MKT-002 데이터 부재 — 거부 + 대표 자가 베타 대안 제안",
          not r["ok"] and "가상 스토리" in r["reason"] and "자가 베타" in r["alternative"],
          str(r))

    # ── MKT-001/003: 3막 초안 + 숫자 포함 + 익명화 + 승인 게이트 ──
    story_fb = feedback_file("fb-story.md", customer="demo", delegation="장보기",
                             satisfaction=5, offline_realized="yes",
                             offline_story="지수가 성수동 공방에서 딸과 도자기를 만들며 흙냄새를 맡았다",
                             delegated_hours=3, reclaimed_hours=3)
    r = marketing.write_story(feedback_path=story_fb)
    draft_text = Path(r["draft"]).read_text(encoding="utf-8") if r.get("ok") else ""
    check("MKT-001 3막 구조 초안 + Reclaimed 숫자 포함 (drafts/)",
          r["ok"] and "1막" in draft_text and "2막" in draft_text and "3막" in draft_text
          and "3" in draft_text and "drafts" in r["draft"], str(r))
    check("MKT-003 익명화 — 이름·동네가 초안에 없음",
          "지수" not in draft_text and "성수동" not in draft_text
          and "고객 A" in draft_text and "동네" in draft_text, draft_text[-200:])
    blocked = marketing.publish(r["draft"], approved=False)
    approved = marketing.publish(r["draft"], approved=True)
    check("MKT-001 승인 게이트 — 미승인 게시 차단, 승인 시 published/ 이동",
          not blocked["ok"] and approved["ok"]
          and Path(approved["published"]).exists()
          and not Path(r["draft"]).exists(), str(blocked))
    # 리허설 산출물 정리 (실 저장소 drafts/published 오염 방지)
    Path(approved["published"]).unlink()

    # ── OPS-001: 대표 지시 — 부문 배정·산출물·반환 4요소 ──
    r = directive.handle("지시: 문진에 수면 질문 추가 검토")
    out_path = ROOT / r["output"]
    check("OPS-001 지시 — 상품기획 배정 + 부문 디렉토리 산출물 + 반환 4요소",
          r["dept"] == "product" and out_path.exists()
          and r["flow"].startswith("flows/") and "맥북 확인" in r["check"]
          and r["next"].startswith("다음 단계 제안"), str(r))
    out_path.unlink()  # 리허설 산출물 정리

    # ── OPS-005: 해지·환불 — 시점별 규정 + 사전 고지 ──
    bprof = onboarding.create_profile({
        "name": "해지테스트", "contact": "bill@example.com", "type": "SFRA",
        "tier": "one", "approval_limit": 30000, "deny_list": [],
        "first_delegation": "메일 정리"})
    bid = bprof["id"]
    r0 = billing.cancel_service(bid)  # 사용량 0 → 전액
    queue._charge_usage(bid, 4.0, bprof)  # 사용 중 상태 (one 한도 10h)
    r1 = billing.cancel_service(bid)
    queue._charge_usage(bid, 7.0, bprof)  # 한도 초과 → 완료 후
    r2 = billing.cancel_service(bid)
    check("OPS-005 시점별 환불 — 전액 / 일할 / 완료 후 분쟁 절차",
          r0["refund"] == billing.TIER_FEES["one"] and "전액" in r0["stage"]
          and 0 < r1["refund"] < billing.TIER_FEES["one"] and "일할" in r1["stage"]
          and r2["refund"] == 0 and "분쟁" in r2["stage"],
          f"{r0['refund']}/{r1['refund']}/{r2['refund']}")
    newp = onboarding.create_profile({
        "name": "사전고지", "contact": "pre@example.com", "type": "SFRA",
        "tier": "one", "approval_limit": 30000, "deny_list": [],
        "first_delegation": "메일 정리"})
    welcome = [m for m in outbox() if "환영" in m["subject"]
               and newp["address"] in m["body"]]
    check("OPS-005 사전 고지 — 환영 메일에 해지·환불 규정 포함",
          welcome and "해지·환불 규정" in welcome[0]["body"]
          and "일할" in welcome[0]["body"])

    # ── ONB-002: 중도 이탈 → 이어하기 (타입 재시행 없음, 중복 질문 없음) ──
    part = onboarding.start_partial({"name": "하다만", "contact": "h@example.com",
                                     "type": "TCRA", "deny_list": []})
    check("ONB-002 부분 프로필 — pending에 남은 항목만, 주소 선발급",
          part["onboarded"] is False
          and set(part["pending"]) == {"tier", "approval_limit", "first_delegation"}
          and "@unplugin.me" in part["address"], str(part["pending"]))
    resumed = onboarding.resume(part["id"], {"tier": "one", "approval_limit": 30000,
                                             "first_delegation": "예약 처리"})
    check("ONB-002 이어하기 — 남은 항목만 질문, 타입 재시행 없음, 완료",
          resumed["onboarded"] is True and resumed["type"] == "TCRA"
          and set(resumed["asked"]) == {"tier", "approval_limit", "first_delegation"}
          and any("타입" in s for s in resumed["skipped"]), str(resumed.get("asked")))

    # ── ONB-006: 미완료 고객의 위임 → 최소 항목 안내, 결제성 위임 미시작 ──
    part2 = onboarding.start_partial({"name": "급한위임", "contact": "rush@example.com",
                                      "type": "SFRA"})
    n_pending_before = len(common.list_queue("pending"))
    drop("rush@example.com", part2["address"], "Fwd: 생수 주문", "늘 먹던 생수 주문해줘")
    res = mailbox.process_inbox()
    gate_mail = [m for m in outbox() if "확인할게요" in m["body"]]
    check("ONB-006 온보딩 미완료 — 최소 항목 안내 + 위임 큐 미생성 (타입 강요 없음)",
          res[0]["action"] == "onboarding_gate"
          and len(common.list_queue("pending")) == n_pending_before
          and gate_mail and "타입 테스트" in gate_mail[0]["body"], str(res))

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
