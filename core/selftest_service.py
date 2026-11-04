"""service 데몬 셀프테스트 — 격리 환경(/tmp)에서 1사이클 리허설.

실행: cd /home/coder/workspace/unplugin && python3 core/selftest_service.py
커버: serve 1사이클 완주(미설정 mail 단계 skip) / inbox→Flow 생성 /
      dashboard.html 생성 / `python3 -m core serve --once` exit 0
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

# ── 반드시 core import 전에 격리 경로 설정 ──────────────────
DATA = Path("/tmp/svc-data")
FLOWS = Path("/tmp/svc-flows")
os.environ["UNPLUGIN_DATA"] = str(DATA)
os.environ["UNPLUGIN_LEGACY_DELEGATION"] = "1"  # 동결된 대행 경로 검증 (피벗 2026-11-04)
os.environ["UNPLUGIN_FLOWS"] = str(FLOWS)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for d in (DATA, FLOWS):
    shutil.rmtree(d, ignore_errors=True)

from core import common, service  # noqa: E402  (환경 설정 후 import)

FIXTURE = ROOT / "tests" / "fixtures" / "mail" / "01-fwd-instruction.md"
_checks: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _checks.append(bool(ok))
    line = f"{'PASS' if ok else 'FAIL'}  {name}"
    if detail and not ok:
        line += f"  [{detail}]"
    print(line)


def _mail_io_configured() -> bool:
    """mail_io 모듈과 설정이 모두 준비됐는지 (skip 로그 기대 여부 판단용)."""
    mod, cfg = service._load_mail_io()
    return mod is not None and cfg is not None


def seed() -> None:
    """demo 프로필·규칙 복사 + 픽스처 메일 1통 투입."""
    common.ensure_dirs()
    src = ROOT / "data" / "customers" / "demo"
    dst = common.CUSTOMERS / "demo"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("profile.json", "rules.json"):
        shutil.copy(src / f, dst / f)
    shutil.copy(FIXTURE, common.INBOX / FIXTURE.name)


def main() -> int:
    seed()

    # ── ① 1사이클이 예외 없이 완료 ──────────────────────────
    buf = io.StringIO()
    exc: Exception | None = None
    code = None
    try:
        with redirect_stdout(buf):
            code = service.run(once=True)
    except Exception as e:  # noqa: BLE001 — 실패 사실 자체를 검증
        exc = e
    out = buf.getvalue()
    print("── service.run(once=True) 출력 ──")
    print(out.rstrip())
    print("──────────────────────────────")

    check("① 사이클이 예외 없이 완료 (exit 0)",
          exc is None and code == 0, f"exc={exc!r}, code={code}")
    cycle_line = re.search(r"mail↓\d+ 처리\d+ 큐\(\d+/\d+/\d+\) mail↑\d+", out)
    check("① 사이클 한 줄 로그 형식 (mail↓n 처리n 큐(승격/실행/대기) mail↑n)",
          bool(cycle_line), f"출력에 사이클 로그 없음: {out!r}")
    if _mail_io_configured():
        check("① mail 단계 — mail_io 설정됨 → skip 불필요 (실연동 모드)", True)
    else:
        check("① mail 단계 skip 로그 (mail_io 미설정 — 시뮬레이션 모드)",
              "skip" in out, f"skip 로그 없음: {out!r}")

    # ── ② inbox 처리 → Flow 생성 ───────────────────────────
    leftover = list(common.INBOX.glob("*.md"))
    flow_files = [p for p in FLOWS.glob("*.md")
                  if p.name not in ("_template.md", "README.md")]
    check("② inbox 메일 처리됨 (inbox 비움)", not leftover, str(leftover))
    check("② Flow 문서 생성", len(flow_files) >= 1,
          f"flows={[p.name for p in FLOWS.glob('*')]}")
    all_q = [it for s in common.QUEUE_STATES for it in common.list_queue(s)]
    check("② 위임 건이 큐에 접수됨", len(all_q) >= 1, f"queue={all_q}")

    # ── ③ dashboard.html 생성 ─────────────────────────────
    check("③ dashboard.html 생성",
          common.DASHBOARD.exists() and common.DASHBOARD.stat().st_size > 0,
          str(common.DASHBOARD))

    # ── ④ CLI 진입점: python3 -m core serve --once → exit 0 ──
    env = dict(os.environ)  # UNPLUGIN_DATA/FLOWS 격리 유지
    proc = subprocess.run(
        [sys.executable, "-m", "core", "serve", "--once"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    check("④ `python3 -m core serve --once` exit 0",
          proc.returncode == 0,
          f"rc={proc.returncode}, stderr={proc.stderr[-300:]!r}")

    ok = all(_checks)
    print(f"\n{'전체 PASS' if ok else 'FAIL 있음'} "
          f"({sum(_checks)}/{len(_checks)})")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        for d in (DATA, FLOWS):
            shutil.rmtree(d, ignore_errors=True)
    sys.exit(code)
