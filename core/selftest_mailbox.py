"""mailbox 파이프라인 셀프테스트 — 격리 환경(/tmp)에서 전 시나리오 리허설.

실행: cd /home/coder/workspace/unplugin && python3 core/selftest_mailbox.py
커버: TC-EML-001(바운스)/002(위임·질문)/003(주간 배치)/004(조건 규칙)/005(격리)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ── 반드시 core import 전에 격리 경로 설정 ──────────────────
DATA = Path("/tmp/mbx-data")
FLOWS = Path("/tmp/mbx-flows")
os.environ["UNPLUGIN_DATA"] = str(DATA)
os.environ["UNPLUGIN_FLOWS"] = str(FLOWS)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for d in (DATA, FLOWS):
    shutil.rmtree(d, ignore_errors=True)

from core import common, flow, mailbox  # noqa: E402  (환경 설정 후 import)

FIXTURES = ROOT / "tests" / "fixtures" / "mail"
_checks: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _checks.append(bool(ok))
    line = f"{'PASS' if ok else 'FAIL'}  {name}"
    if detail and not ok:
        line += f"  [{detail}]"
    print(line)


def outbox_mails() -> list[dict]:
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def main() -> int:
    # 격리 환경 준비: demo 프로필·규칙 복사, 픽스처 투입
    common.ensure_dirs()
    src = ROOT / "data" / "customers" / "demo"
    dst = common.CUSTOMERS / "demo"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("profile.json", "rules.json"):
        shutil.copy(src / f, dst / f)
    for p in sorted(FIXTURES.glob("*.md")):
        shutil.copy(p, common.INBOX / p.name)

    results = {r["mail"]: r for r in mailbox.process_inbox()}
    mails = outbox_mails()
    q_names = {p.name for p in common.QUARANTINE.glob("*.md")}
    pending = common.list_queue("pending")

    # ── ⑥⑦⑧ 격리 3건: quarantine 보관 + 자동 실행 0건 + 고객 통지 ──
    bad = ("08-unknown-urgent.md", "09-spoof-authfail.md", "10-injection.md")
    check("⑥⑦⑧ 격리 3건이 quarantine에 보관됨",
          all(b in q_names for b in bad), f"quarantine={sorted(q_names)}")
    check("⑥⑦⑧ 결과 action=quarantined",
          all(results[b]["action"] == "quarantined" for b in bad),
          str({b: results[b]["action"] for b in bad}))
    notices = [m for m in mails if "메일 격리 안내" in m["subject"]]
    check("⑥⑦⑧ 격리 고객 통지 3통 발송", len(notices) == 3, f"{len(notices)}통")
    check("자동 실행 0건 (pending 큐는 위임·규칙 2건뿐)",
          len(pending) == 2
          and sorted(p["kind"] for p in pending) == ["delegation", "rule"],
          str([(p["id"], p["kind"]) for p in pending]))

    # ── ① 포워딩+지시 → delegated (flow + pending 큐) ──
    r1 = results["01-fwd-instruction.md"]
    deleg = [p for p in pending if p["kind"] == "delegation"]
    check("① delegated — flow + pending 큐 생성",
          r1["action"] == "delegated" and len(deleg) == 1
          and flow.flow_path(deleg[0]["flow"]).exists()
          and deleg[0]["amount"] == 54000,
          f"result={r1}, queue={deleg}")

    # ── ② 포워딩 모호 → clarify 1회 ──
    r2 = results["02-fwd-ambiguous.md"]
    asks = [m for m in mails if "무엇을 도와드릴까요" in m["body"]]
    check("② clarify — 질문 1회만 발송",
          r2["action"] == "clarify" and len(asks) == 1,
          f"result={r2}, 질문 {len(asks)}통")

    # ── ④ 9% → archived·메일 없음 / ⑤ 15% → rule_triggered ──
    r4 = results["06-bill-9pct.md"]
    archived = {p.name for p in (common.CUSTOMERS / "demo" / "archive").glob("*.md")}
    no_mail_for_9 = not any("증가율: 9%" in m["body"] or "49050" in m["body"]
                            for m in mails)
    check("④ 9% — archived·보관 파일 있음·고객 메일 없음",
          r4["action"] == "archived" and "06-bill-9pct.md" in archived
          and no_mail_for_9,
          f"result={r4}, archive={sorted(archived)}")
    r5 = results["07-bill-15pct.md"]
    rule_items = [p for p in pending if p["kind"] == "rule"]
    check("⑤ 15% — rule_triggered (flow + 큐, 규칙 발동은 이 1건뿐)",
          r5["action"] == "rule_triggered" and len(rule_items) == 1
          and flow.flow_path(rule_items[0]["flow"]).exists(),
          f"result={r5}, rule_items={rule_items}")

    # ── ③ 가정통신문 3통 → batch 적재 → 주간 요약 1통 ──
    school = ("03-school-1.md", "04-school-2.md", "05-school-3.md")
    bfiles = list((common.CUSTOMERS / "demo" / "batch").glob("*.jsonl"))
    n_lines = (len([l for l in bfiles[0].read_text(encoding="utf-8").splitlines()
                    if l.strip()]) if bfiles else 0)
    check("③ 3통 batched — jsonl 1개에 3줄 적재",
          all(results[s]["action"] == "batched" for s in school)
          and len(bfiles) == 1 and n_lines == 3,
          f"files={bfiles}, lines={n_lines}")
    batch_results = mailbox.process_weekly_batches(force=True)
    mails_after = outbox_mails()
    summaries = [m for m in mails_after
                 if m["subject"].startswith("[Unplugin] 주간 요약")]
    check("③ 주간 요약 메일 1통 + jsonl 삭제",
          len(summaries) == 1 and len(batch_results) == 1
          and not list((common.CUSTOMERS / "demo" / "batch").glob("*.jsonl")),
          f"summaries={len(summaries)}, batch_results={batch_results}")

    # ── ⑨ 미발급 주소 → bounce ──
    r9 = results["11-unknown-address.md"]
    check("⑨ 미발급 주소 — bounce·격리 보관",
          r9["action"] == "bounce" and "11-unknown-address.md" in q_names,
          f"result={r9}")

    # inbox는 모두 비워져야 함 (이동 또는 삭제)
    leftover = list(common.INBOX.glob("*.md"))
    check("inbox 비움 (처리 후 삭제/이동)", not leftover, str(leftover))

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
