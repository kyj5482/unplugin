"""실행기 셀프테스트 — `python3 core/selftest_executor.py` 로 실행.

임시 디렉토리에 UNPLUGIN_DATA / UNPLUGIN_FLOWS를 격리한 뒤 core를 import 한다.
브라우저가 없는 개발 환경 기준: 시뮬레이션 경로만으로 전부 PASS 해야 한다.

검증 항목:
  ① 시뮬레이션 run이 ok / summary / reclaimed / mode=simulated 계약 준수
  ② 플러그인 est_hours_per_week 반영 (item est_hours가 우선)
  ③ evidence_note 문구 (증빙 없음 — 시뮬레이션 / 증빙 N건: 경로)
  ④ UNPLUGIN_REAL_BROWSER=1 이지만 playwright 미설치 → 조용히 simulated 폴백
  ⑤ queue.run_tick 통합: amount 0 아이템이 executor 경유로 done + Flow에 증빙 노트
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 격리: core import "전에" 환경변수 설정 ─────────────────
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-exec-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ.pop("UNPLUGIN_REAL_BROWSER", None)
sys.path.insert(0, str(ROOT))

from core import common, executor, flow, queue as q  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def main() -> int:
    common.ensure_dirs()

    # ── ① 시뮬레이션 run 계약 ────────────────────────────
    item1 = {"id": "t-exec-1", "kind": "delegation",
             "summary": "세탁 수거 예약", "est_hours": 0}
    r1 = executor.run(item1, {})
    check("① 시뮬레이션 run: ok=True / mode=simulated",
          r1["ok"] is True and r1["mode"] == "simulated", str(r1))
    check("① summary 형식 유지 (기존 체크 문자열 '처리 완료' 포함)",
          r1["summary"] == "세탁 수거 예약 처리 완료 (v0 시뮬레이션 — 증빙 없음)",
          r1["summary"])
    check("① evidence=[] / reclaimed 기본 0.5",
          r1["evidence"] == [] and r1["reclaimed"] == 0.5,
          f"evidence={r1['evidence']} reclaimed={r1['reclaimed']}")

    # ── ② 플러그인 est_hours 반영 ────────────────────────
    item2 = {"id": "t-exec-2", "kind": "plugin:grocery-recurring",
             "summary": "생수 정기주문"}  # 카탈로그: est_hours_per_week=1.5
    r2 = executor.run(item2, {})
    check("② plugin:grocery-recurring → 장보기 시뮬(est 1.5 + 영수증 증빙 + 예산 내)",
          r2["mode"] == "sim-cart" and r2["reclaimed"] == 1.5
          and r2["ok"] and len(r2["evidence"]) == 1
          and "예산" in r2["summary"],
          f"r2={r2}")
    item2b = dict(item2, est_hours=2.0)
    r2b = executor.run(item2b, {})
    check("② item의 est_hours가 있으면 그것이 우선 (2.0)",
          r2b["reclaimed"] == 2.0, f"reclaimed={r2b['reclaimed']}")
    item2c = {"id": "t-exec-2c", "kind": "plugin:없는-플러그인", "summary": "미지 업무"}
    r2c = executor.run(item2c, {})
    check("② 카탈로그에 없는 plugin id → 폴백 0.5 + ok",
          r2c["ok"] and r2c["reclaimed"] == 0.5, str(r2c))

    # ── ③ evidence_note 문구 ─────────────────────────────
    check("③ 시뮬레이션 결과 → \"증빙 없음 — 시뮬레이션\"",
          executor.evidence_note(r1) == "증빙 없음 — 시뮬레이션",
          executor.evidence_note(r1))
    fake = {"ok": True, "mode": "browser",
            "evidence": [str(common.DATA / "evidence" / "x" / "step1.png"),
                         str(common.DATA / "evidence" / "x" / "step2.png")]}
    note = executor.evidence_note(fake)
    check("③ 증빙 2건 → \"증빙 2건: ...step1.png...\"",
          note.startswith("증빙 2건: ") and "step1.png" in note and "step2.png" in note,
          note)

    # ── ④ REAL_BROWSER=1 + playwright 미설치 → 조용한 폴백 ──
    saved = {k: sys.modules.get(k) for k in ("playwright", "playwright.sync_api")}
    sys.modules["playwright"] = None          # import 강제 실패 (설치돼 있어도 동일 재현)
    sys.modules["playwright.sync_api"] = None
    os.environ["UNPLUGIN_REAL_BROWSER"] = "1"
    try:
        r4 = executor.run({"id": "t-exec-4", "kind": "plugin:grocery-recurring",
                           "summary": "생수 정기주문"}, {})
    finally:
        os.environ.pop("UNPLUGIN_REAL_BROWSER", None)
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    check("④ UNPLUGIN_REAL_BROWSER=1 + playwright 없음 → 시뮬 폴백 (예외 없음)",
          r4["ok"] is True and r4["mode"] == "sim-cart",
          str(r4))

    # ── ⑤ queue.run_tick 통합 (amount=0 → executor 경유 done) ──
    common.write_json(common.CUSTOMERS / "demo" / "profile.json", {
        "id": "demo", "name": "데모", "address": "demo.a1b2@unplugin.me",
        "contact": "demo@example.com", "type": "SFRA", "tier": "one",
        "approval_limit": 30000, "deny_list": [], "trusted_senders": [],
        "onboarded": True,
    })
    fid = flow.create_flow("demo", "메일함 정리", "delegation", "셀프테스트: 메일함 정리")
    iid = q.enqueue("demo", "plugin:inbox-cleanup", "메일함 정리", fid)  # amount=0
    q.run_tick()
    done = common.queue_item_path("done", iid)
    ftext = flow.flow_path(fid).read_text(encoding="utf-8")
    check("⑤ amount 0 아이템이 run_tick으로 done 이동",
          done.exists() and common.read_json(done).get("charged") is True)
    check("⑤ Flow에 실행 요약 + 증빙 노트 포함",
          "실행 요약: 메일함 정리 처리 완료 (v0 시뮬레이션 — 증빙 없음)" in ftext
          and "증빙 없음 — 시뮬레이션" in ftext)
    check("⑤ 플러그인 est_hours(0.5)로 완결·사용량 차감",
          "**예상/실측 Reclaimed Hours**: 0.5" in ftext
          and common.read_json(q.usage_path("demo"))["monthly"]
              .get(common.now().strftime("%Y-%m")) == 0.5)

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
