"""Admin·측정 보정 셀프테스트 — TC-ADM-001~004.

피벗 기본 모드(보고 자동 적립)에서 개인 보정(time_factor)·산정 근거(basis)·
admin.html 생성을 검증한다. 실행: python3 -m core.selftest_admin (격리 /tmp)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-adm-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
os.environ["UNPLUGIN_REPORTS"] = str(_TMP / "reports")
os.environ.pop("UNPLUGIN_LEGACY_DELEGATION", None)
sys.path.insert(0, str(ROOT))

from core import admin, common, dividend, mailbox  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def put_profile(cid: str, **extra) -> dict:
    prof = {"id": cid, "name": cid, "address": f"{cid}.t3st@unplugin.me",
            "contact": f"{cid}@example.com", "type": "SFRA", "tier": "one",
            "approval_limit": 30000, "deny_list": [], "onboarded": True,
            "trusted_senders": ["muze@agentmail.example"], **extra}
    common.write_json(common.CUSTOMERS / cid / "profile.json", prof)
    return prof


def drop(frm, to, subject, body):
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    p.write_text(f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\n---\n\n{body}\n",
                 encoding="utf-8")


def outbox():
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def main() -> int:
    common.ensure_dirs()
    prof = put_profile("adm", region="성수동")

    # ADM-001: 적립에 basis(기준치·보정·근거) 기록, 기본 factor 1.0
    drop("muze@agentmail.example", prof["address"], "[보고] 생필품 정기 주문 완료",
         "생수 정기 주문 완료했어.")
    mailbox.process_inbox()
    led = dividend.load_ledger("adm")
    ev = led["events"][-1]
    check("ADM-001 basis 기록 — baseline·factor·evidence",
          ev["basis"]["factor"] == 1.0 and ev["basis"]["baseline"] == ev["saved_minutes"]
          and ev["basis"]["evidence"].startswith("ops/research-time-baselines.md#"),
          str(ev.get("basis")))

    # ADM-002: calibrate 적용 + 클램프
    admin.calibrate("adm", 1.5)
    drop("muze@agentmail.example", prof["address"], "[보고] 식당 예약 완료",
         "식당 예약 완료했어.")
    mailbox.process_inbox()
    ev2 = dividend.load_ledger("adm")["events"][-1]
    ok_f = ev2["basis"]["factor"] == 1.5 and ev2["saved_minutes"] == round(ev2["basis"]["baseline"] * 1.5)
    hi = admin.calibrate("adm", 9.9)["time_factor"]
    lo = admin.calibrate("adm", 0.01)["time_factor"]
    check("ADM-002 개인 보정 — ×1.5 적용 + 0.5~2.0 클램프",
          ok_f and hi == 2.0 and lo == 0.5, f"{ev2['saved_minutes']} hi={hi} lo={lo}")

    # ADM-003: 적립 메일에 산정 근거 줄
    acc = [m for m in outbox() if "시간 배당 적립" in m["subject"]]
    check("ADM-003 적립 메일 — 산정 근거(기준치×보정·출처) 명시",
          acc and all("산정 근거" in m["body"] and "ops/research-time-baselines.md" in m["body"]
                      for m in acc)
          and "× 개인 보정 ×1.5" in acc[-1]["body"], acc[-1]["body"][-120:] if acc else "없음")

    # ADM-004: admin.html — 잔고·피드·미매칭 백로그 포함
    admin.calibrate("adm", 1.0)
    drop("muze@agentmail.example", prof["address"], "[보고] 어항 물갈이 완료",
         "어항 물갈이 끝냈어.")
    mailbox.process_inbox()
    path = admin.generate()
    html = path.read_text(encoding="utf-8")
    check("ADM-004 admin.html — 잔고·에이전트 피드·미매칭 백로그",
          path.exists() and "시간 배당 잔고" in html and "Muze" in html
          and "미매칭 보고" in html and "어항 물갈이" in html and "성수동" in html)

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
