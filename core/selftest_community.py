"""커뮤니티 셀프테스트 — TC-CMU-001~004.

공통 위임 특성 기반 그룹 편성·익명 다이제스트·지역 모임 제안을 검증한다.
실행: python3 -m core.selftest_community (격리 /tmp)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-cmu-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ["UNPLUGIN_REPORTS"] = str(_TMP / "reports")
os.environ.pop("UNPLUGIN_LEGACY_DELEGATION", None)
sys.path.insert(0, str(ROOT))

from core import common, community, dividend, mailbox  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def put_profile(cid: str, name: str, **extra) -> dict:
    prof = {"id": cid, "name": name, "address": f"{cid}.t3st@unplugin.me",
            "contact": f"{cid}@example.com", "type": "SFRA", "tier": "one",
            "approval_limit": 30000, "deny_list": [], "onboarded": True,
            "trusted_senders": ["muze@agentmail.example"], **extra}
    common.write_json(common.CUSTOMERS / cid / "profile.json", prof)
    return prof


def report(prof: dict, subject: str, body: str) -> None:
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    p.write_text(f"---\nfrom: muze@agentmail.example\nto: {prof['address']}\n"
                 f"subject: [보고] {subject}\n---\n\n{body}\n", encoding="utf-8")
    mailbox.process_inbox()


def outbox():
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def main() -> int:
    common.ensure_dirs()
    a = put_profile("cm-a", "가영", region="성수동", movement_threshold_minutes=60)
    b = put_profile("cm-b", "나율", region="성수동")
    c = put_profile("cm-c", "다온")  # region 없음

    # 같은 유형(쇼핑) 적립 — 그룹 성립
    report(b, "생필품 정기 주문 완료", "생수 정기 주문 완료했어.")
    report(c, "생필품 정기 주문 완료", "생수 정기 주문 완료했어.")

    # CMU-001: 그룹 자동 편성 (a는 2건 적립 — 40+40분으로 임계치 60 돌파 → 제안)
    report(a, "생필품 정기 주문 완료", "생수 정기 주문 완료했어.")
    report(a, "생필품 정기 주문 완료", "기저귀 정기 주문도 완료했어.")
    groups = community.memberships()
    shop = groups.get("쇼핑", [])
    check("CMU-001 그룹 자동 편성 — 같은 유형 위임자 묶임",
          {m["customer"] for m in shop} == {"cm-a", "cm-b", "cm-c"}, str(groups.keys()))

    # CMU-002: 지역 모임 섹션 — 같은 region 2명 이상일 때만
    moves = [m for m in outbox() if "무브먼트" in m["subject"] and a["contact"] == m["to"]]
    check("CMU-002 무브먼트 제안에 동네 모임 섹션 — 같은 그룹·같은 지역",
          moves and "같은 그룹 모임 제안" in moves[-1]["body"]
          and "성수동" in moves[-1]["body"], moves[-1]["body"][-150:] if moves else "제안 없음")
    check("CMU-002b 모임 섹션 익명 — 이웃 실명·주소 미노출",
          moves and "나율" not in moves[-1]["body"]
          and b["address"] not in moves[-1]["body"])

    # CMU-003: 다이제스트 — 멤버 전원 1통, 익명 닉네임, 주기 중복 방지
    n0 = len(outbox())
    r1 = community.run_tick(force=True)
    digests = [m for m in outbox()[n0:] if "다이제스트" in m["subject"]]
    sent_groups = [r for r in r1 if r["sent"]]
    anon_ok = all(("가1" in m["body"] or "가" in m["body"]) and "cm-a" not in m["body"]
                  and a["address"] not in m["body"] for m in digests)
    check("CMU-003 다이제스트 — 그룹 전원 발송 + 익명 닉네임만",
          sent_groups and len(digests) == 3 and anon_ok,
          f"{len(digests)}통 / {sent_groups}")
    r2 = community.run_tick()  # 주기 미도래 → 전부 건너뜀
    check("CMU-003b 주기 중복 방지 — 7일 내 재발송 없음",
          all(not r["sent"] for r in r2), str(r2))

    # CMU-004: region 없는 고객 — 모임 섹션 없음
    sec = community.meetup_section("cm-c")
    check("CMU-004 지역 미등록 고객 — 모임 제안 없음", sec == "", sec)

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
