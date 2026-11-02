"""dashboard/cli 셀프테스트 — 격리 환경에서 Flow 2개 생성 후 대시보드 검증.

실행: python3 core/selftest_dashboard.py
격리: UNPLUGIN_DATA=/tmp/dsh-data, UNPLUGIN_FLOWS=/tmp/dsh-flows (core import 전 설정)
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TMP_DATA = "/tmp/dsh-data"
TMP_FLOWS = "/tmp/dsh-flows"

# core import 전에 격리 환경변수 설정 (common.py가 import 시점에 경로를 읽음)
os.environ["UNPLUGIN_DATA"] = TMP_DATA
os.environ["UNPLUGIN_FLOWS"] = TMP_FLOWS

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core import common, dashboard, flow  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((ok, name))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, UNPLUGIN_DATA=TMP_DATA, UNPLUGIN_FLOWS=TMP_FLOWS)
    return subprocess.run([sys.executable, "-m", "core", *args],
                          cwd=REPO, env=env, capture_output=True, text=True)


def main() -> int:
    # ── 격리 환경 준비 ──
    for d in (TMP_DATA, TMP_FLOWS):
        shutil.rmtree(d, ignore_errors=True)
    common.ensure_dirs()
    Path(TMP_FLOWS).mkdir(parents=True, exist_ok=True)

    # demo 프로필 복사 (notify가 프로필을 조회함)
    src = REPO / "data" / "customers" / "demo"
    shutil.copytree(src, Path(TMP_DATA) / "customers" / "demo")

    try:
        # ── Flow 1: 완료 (reclaimed 2.5h) ──
        f1 = flow.create_flow("demo", "통신비 인상 이의신청", "고객 요청",
                              "이번 달 통신 요금 왜 올랐는지 확인하고 이의신청까지 해줘")
        flow.add_step(f1, "it", "요금 내역 조회 · 작년 대비 18% 인상 확인")
        flow.complete(f1, "이의신청 접수 완료 — 34,000원 환급 예정", reclaimed_hours=2.5)

        # ── Flow 2: 확인 필요 ──
        f2 = flow.create_flow("demo", "주말 공방 클래스 예약", "고객 요청",
                              "토요일 오후 도자기 공방 예약해줘")
        flow.ask_customer(f2, "토요일 14시와 16시 중 어느 시간이 좋으세요?")

        t1 = "통신비 인상 이의신청"
        t2 = "주말 공방 클래스 예약"

        # ── 대시보드 생성 ──
        out = dashboard.generate()
        html = out.read_text(encoding="utf-8") if out.exists() else ""

        # 1) HTML 파일 존재
        check("HTML 파일 존재 (common.DASHBOARD)",
              out == common.DASHBOARD and out.exists() and len(html) > 0)

        # 2) 두 Flow 제목 포함
        check("두 Flow 제목 포함", t1 in html and t2 in html)

        # 3) '확인 필요' 분리 섹션에 해당 Flow
        m = re.search(r'<section class="attention" id="attention">(.*?)</section>',
                      html, re.S)
        att = m.group(1) if m else ""
        check("'확인 필요' 섹션에 해당 Flow 강조",
              bool(m) and t2 in att and t1 not in att,
              "attention 섹션 누락 또는 내용 불일치")

        # 4) Reclaimed 합계 2.5 표기
        check("Reclaimed 합계 2.5 표기", 'data-stat="reclaimed">2.5<' in html)

        # 5) 상태 배지 수 일치 (스탯 칩 수치 = 실제 배지 수)
        expected = {"완료": 1, "확인 필요": 1, "접수": 0, "진행 중": 0, "취소": 0}
        badge_cls = {"완료": "st-done", "확인 필요": "st-ask", "접수": "st-new",
                     "진행 중": "st-run", "취소": "st-cancel"}
        ok5, why = True, []
        for status, n in expected.items():
            chip = re.search(rf'data-stat="{status}">(\d+)<', html)
            n_chip = int(chip.group(1)) if chip else -1
            n_badge = html.count(f'class="badge {badge_cls[status]}"')
            if not (n_chip == n_badge == n):
                ok5 = False
                why.append(f"{status}: 칩={n_chip} 배지={n_badge} 기대={n}")
        check("상태 배지 수 일치", ok5, "; ".join(why))

        # 6) CLI exit 0
        r_status = run_cli("status")
        check("python3 -m core status → exit 0", r_status.returncode == 0,
              r_status.stderr.strip()[:200])
        r_dash = run_cli("dashboard")
        check("python3 -m core dashboard → exit 0", r_dash.returncode == 0,
              r_dash.stderr.strip()[:200])

    finally:
        for d in (TMP_DATA, TMP_FLOWS):
            shutil.rmtree(d, ignore_errors=True)

    n_pass = sum(1 for ok, _ in RESULTS if ok)
    print(f"\n결과: {n_pass}/{len(RESULTS)} PASS")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
