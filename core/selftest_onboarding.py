"""onboarding.py + kpi.py 셀프테스트 — 격리 환경(/tmp)에서 실행 후 정리.

실행: python3 core/selftest_onboarding.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# ── 격리: core import 전에 환경변수 설정 (common.py가 import 시점에 경로를 고정) ──
TMP_DATA = "/tmp/onb-data"
TMP_FLOWS = "/tmp/onb-flows"
TMP_REPORTS = "/tmp/onb-reports"
os.environ["UNPLUGIN_DATA"] = TMP_DATA
os.environ["UNPLUGIN_FLOWS"] = TMP_FLOWS
os.environ["UNPLUGIN_REPORTS"] = TMP_REPORTS
for d in (TMP_DATA, TMP_FLOWS, TMP_REPORTS):
    shutil.rmtree(d, ignore_errors=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import common, kpi, onboarding  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    demo = common.read_json(FIXTURES / "onboard-demo.json")

    # ① create_profile: profile.json·난수 주소·환영 메일·온보딩 Flow
    profile = onboarding.create_profile(dict(demo))
    pfile = common.CUSTOMERS / profile["id"] / "profile.json"
    check("① profile.json 생성 (onboarded=true)",
          pfile.exists() and common.read_json(pfile).get("onboarded") is True, str(pfile))
    check("① rules.json 생성", (common.CUSTOMERS / profile["id"] / "rules.json").exists())
    addr_ok = bool(re.fullmatch(rf"{re.escape(profile['id'])}\.[0-9a-f]{{4}}@unplugin\.me",
                                profile["address"]))
    check("① 주소 난수 슬러그 패턴 (<id>.<hex4>@unplugin.me)", addr_ok, profile["address"])
    welcome = [p for p in sorted(common.OUTBOX.glob("*.md"))
               if profile["address"] in p.read_text(encoding="utf-8")
               and "포워딩" in p.read_text(encoding="utf-8")]
    check("① 환영 메일 1통 (발급 주소 + 포워딩 안내 포함)", len(welcome) == 1,
          f"{len(welcome)}통")
    flows = list(common.FLOWS.glob("*.md"))
    onb_flows = [f for f in flows if "온보딩" in f.read_text(encoding="utf-8")
                 and profile["id"] in f.read_text(encoding="utf-8")]
    check("① 온보딩 Flow 존재 (단계 기록 포함)",
          len(onb_flows) >= 1 and "첫 위임 확정" in onb_flows[0].read_text(encoding="utf-8"))

    # ② first_delegation 리스트 → ValueError (UC-A4)
    bad = dict(demo)
    bad["first_delegation"] = ["장보기 주문", "예약", "메일 정리"]
    try:
        onboarding.create_profile(bad)
        check("② first_delegation 리스트 → ValueError", False, "예외 없음")
    except ValueError as e:
        check("② first_delegation 리스트 → ValueError", "한 번에 한 가지만" in str(e), str(e)[:60])

    # ③ deny_list와 충돌하는 first_delegation → ValueError (UC-A3)
    bad = dict(demo)
    bad["first_delegation"] = "뉴스레터 읽기"
    try:
        onboarding.create_profile(bad)
        check("③ deny_list 충돌 first_delegation → ValueError", False, "예외 없음")
    except ValueError as e:
        check("③ deny_list 충돌 first_delegation → ValueError", "UC-A3" in str(e), str(e)[:60])

    # ④ check_deny: 금지 항목 True / 허용 항목 False
    deny_hit = onboarding.check_deny(profile, "이번 주 뉴스레터 읽기도 맡길게요")
    deny_miss = onboarding.check_deny(profile, "식료품 장보기 주문 부탁해요")
    check("④ check_deny 금지 True / 허용 False", deny_hit is True and deny_miss is False)

    # ⑤ suggest_offline: reason에 타입 축 근거 (SFRA → R축·A축)
    sug = onboarding.suggest_offline(profile)
    check("⑤ suggest_offline 근거에 타입 축 인용",
          "R축(쉼·감각)" in sug["reason"] and "A축(혼자)" in sug["reason"] and bool(sug["title"]),
          sug["reason"][:60])

    # ⑥ validate_feedback: 정상 픽스처 0건 누락 + 필드 누락 검출
    fixtures_fb = sorted((FIXTURES / "feedback").glob("*.md"))
    all_clean = all(kpi.validate_feedback(p) == [] for p in fixtures_fb)
    check("⑥ 정상 픽스처 3건 누락 0", all_clean and len(fixtures_fb) == 3)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tf:
        tf.write("---\ndelegation: 장보기\nsatisfaction: 4\noffline_realized: yes\n"
                 "reclaimed_hours: 1.0\n---\n본문\n")
        broken = Path(tf.name)
    try:
        missing = kpi.validate_feedback(broken)
        check("⑥ 필드(offline_story) 누락 검출", missing == ["offline_story"], str(missing))
    finally:
        broken.unlink(missing_ok=True)

    # ⑦ aggregate: Delegated 9.0 / Reclaimed 5.5 / 전환율 61% 근사 + 리포트·핸드오프
    agg = kpi.aggregate(FIXTURES / "feedback")
    check("⑦ Delegated 9.0 / Reclaimed 5.5",
          agg["delegated"] == 9.0 and agg["reclaimed"] == 5.5,
          f"delegated={agg['delegated']}, reclaimed={agg['reclaimed']}")
    check("⑦ 전환율 61% 근사", abs(agg["conversion"] - 61.1) < 1.0, f"{agg['conversion']}%")
    report = Path(agg["report"])
    rtext = report.read_text(encoding="utf-8") if report.exists() else ""
    check("⑦ 리포트 파일 생성 (UNPLUGIN_REPORTS 경로)",
          report.exists() and report.parent == Path(TMP_REPORTS), str(report))
    check("⑦ no 건 핸드오프 섹션 (원인: 추천 부적합)",
          "상품기획 핸드오프" in rtext and "추천 부적합" in rtext)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n결과: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS"
          + (f" — 실패 {len(failed)}건" if failed else " — 전부 통과"))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        for d in (TMP_DATA, TMP_FLOWS, TMP_REPORTS):
            shutil.rmtree(d, ignore_errors=True)
    sys.exit(code)
