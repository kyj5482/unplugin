"""데모 러너 — demo/emails 100통 중 1건을 골라 전 과정을 단계별로 시연 (TC-STR-008).

`python3 -m core demo-run <n>` 은 demo/runtime/ 격리 환경(서브프로세스 +
UNPLUGIN_DATA/FLOWS 오버라이드)에서 실행되므로 실데이터·flows/를 오염시키지
않는다. 각 단계가 번호와 함께 출력되어, 클로드 CLI(또는 대표)가 Step-by-Step으로
업무가 처리되는지 눈으로 확인할 수 있다. 실행 후 demo/runtime/ 아래의
flow·케이스·증빙 파일을 직접 열어볼 수 있다.

시나리오 수명주기 (유형 채널에 따라 자동 분기):
  email  — 접수 → 협상 1차 → (상대 거부) → 2차 → (상대 수락) → 추적 → 입금 확인 → 완결
  portal — 접수 → egolite 포털 수행·증빙 → 추적 → 포털 재확인 → 완결
  blocked포털 — 접수 → 봇 차단 감지 → 사람 개입 가이드 → 완료 보고 → 추적 → 고객 확인 → 완결
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import common

DEMO_DIR = common.ROOT / "demo"
RUNTIME = DEMO_DIR / "runtime"


def _index() -> list[dict]:
    return json.loads((DEMO_DIR / "index.json").read_text(encoding="utf-8"))["emails"]


def list_demos() -> None:
    by_type: dict[str, list[dict]] = {}
    for e in _index():
        by_type.setdefault(e["type"], []).append(e)
    print(f"데모 이메일 {sum(len(v) for v in by_type.values())}통 — "
          "실행: python3 -m core demo-run <번호>\n")
    for t, rows in by_type.items():
        print(f"■ {t} ({rows[0]['channel']})")
        for e in rows:
            amt = f" · {e['amount']:,}원" if e["amount"] else ""
            print(f"  {e['n']:>3}. {e['title']}{amt} — {e['situation']}")
        print()


def run(n: int, fresh: bool = False) -> int:
    """격리 환경 서브프로세스로 demo-exec 실행 (common 경로 상수 재적용을 위해)."""
    if fresh and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    env = dict(os.environ)
    env["UNPLUGIN_DATA"] = str(RUNTIME / "data")
    env["UNPLUGIN_FLOWS"] = str(RUNTIME / "flows")
    env["UNPLUGIN_REPORTS"] = str(RUNTIME / "reports")
    # 데모 100통은 동결된 대행 경로의 재생이다 (피벗 전 시나리오)
    env["UNPLUGIN_LEGACY_DELEGATION"] = "1"
    return subprocess.call([sys.executable, "-m", "core", "demo-exec", str(n)],
                           env=env, cwd=str(common.ROOT))


# ── 이하: 격리 env 안에서 실행되는 본체 ─────────────────────

_STEP = 0


def _step(title: str) -> None:
    global _STEP
    _STEP += 1
    print(f"\n[{_STEP}단계] {title}")
    print("─" * 60)


def _tail_outbox(k: int = 1) -> None:
    mails = sorted(common.OUTBOX.glob("*.md"))
    for p in mails[-k:]:
        m = common.parse_mail(p)
        print(f"  ✉ → {m['to']} | {m['subject']}")
        body = m["body"].splitlines()
        for line in body[:4]:
            print(f"    {line}")
        if len(body) > 4:
            print("    …")


def _drop_mail(frm: str, to: str, subject: str, body: str, thread: str = "") -> None:
    common.ensure_dirs()
    p = common.INBOX / f"{common.now().strftime('%Y%m%d-%H%M%S-%f')}-{common.slug(subject)}.md"
    head = f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\n"
    if thread:
        head += f"thread: {thread}\n"
    p.write_text(head + "---\n\n" + body + "\n", encoding="utf-8")


def exec_scenario(n: int) -> int:
    from . import cases as cases_mod, flow, hitl, mailbox, queue, tracking
    entry = next((e for e in _index() if e["n"] == n), None)
    if entry is None:
        print(f"데모 {n}번 없음 (1~{len(_index())})")
        return 1

    # 격리 환경 준비 — 데모 고객 프로필 복사
    common.ensure_dirs()
    src = common.ROOT / "data" / "customers" / "demo"
    dst = common.CUSTOMERS / "demo"
    if not dst.exists():
        shutil.copytree(src, dst)
    prof = common.read_json(dst / "profile.json")

    print("=" * 60)
    print(f"데모 {n}: {entry['title']} ({entry['type']} / {entry['channel']})")
    print(f"상황: {entry['situation']}")
    print(f"격리 환경: {common.DATA}")
    print("=" * 60)

    _step("고객이 메일을 전용 주소로 포워딩 (inbox 투입)")
    mail_text = (DEMO_DIR / entry["file"]).read_text(encoding="utf-8")
    (common.INBOX / Path(entry["file"]).name).write_text(mail_text, encoding="utf-8")
    print(f"  {entry['file']} → {prof['address']}")

    _step("컨시어지(아루) 수신 파이프라인 — 식별·검증·스트레스 유형 분류")
    for r in mailbox.process_inbox():
        print(f"  {r['action']}: {r['detail']}")
    case = (cases_mod.list_cases("open") or [None])[0]
    if case is None:
        print("  케이스가 생성되지 않았어요 — 시나리오 종료")
        return 1
    fid = case["flow"]
    print(f"  케이스 {case['id']} (담당 {case['assignee']}, 우선순위 {case['priority']})")

    _step("큐 1틱 — 스트레스 케이스 최우선 착수")
    print(f"  {queue.run_tick()}")
    case = cases_mod.load(case["id"])
    print(f"  케이스 상태: {case['status']}")
    _tail_outbox(1)

    ch = entry["channel"]
    if ch == "email" or (ch == "hybrid" and case["status"] == "negotiating"):
        merchant = case["intent"].get("merchant_email", "cs@merchant.example")
        _step("상대방 회신 ① — 거부 (\"규정상 불가\")")
        _drop_mail(merchant, prof["address"], f"RE: 환불 요청 (케이스 {case['id']})",
                   "내부 규정상 환불이 불가합니다.", thread=fid)
        for r in mailbox.process_inbox():
            print(f"  {r['action']}: {r['detail']}")
        _tail_outbox(1)

        _step("상대방 회신 ② — 수락 (\"환불 처리하겠습니다\")")
        _drop_mail(merchant, prof["address"], f"RE: 환불 요청 (케이스 {case['id']})",
                   "검토 결과 요청하신 환불 처리하겠습니다. 영업일 3일 내 입금 예정입니다.",
                   thread=fid)
        for r in mailbox.process_inbox():
            print(f"  {r['action']}: {r['detail']}")

        _step("완료 추적 — 환불은 '입금 확인'까지가 완료")
        _drop_mail(merchant, prof["address"], f"RE: 환불 완료 (케이스 {case['id']})",
                   "요청하신 금액의 환불 완료되었습니다. 입금되었으니 확인 바랍니다.",
                   thread=fid)
        for r in mailbox.process_inbox():
            print(f"  {r['action']}: {r['detail']}")
        print(f"  track-run: {tracking.run_tick()}")

    else:  # portal / hybrid(포털 접수형)
        case = cases_mod.load(case["id"])
        if case["status"] == "handoff":
            _step("봇 차단 포털 — 사람 개입(HITL) 가이드 발행 (하루)")
            for st in hitl.list_open():
                print(f"  가이드: data/handoff/{st['id']}.md — {st['reason']}")
                guide = (common.HANDOFF / f"{st['id']}.md").read_text(encoding="utf-8")
                for line in guide.splitlines():
                    if line[:2].rstrip(".").isdigit() or line.startswith("## 따라"):
                        print(f"    {line}")
            _step("직원이 수동 처리 후 완료 보고 (hitl-done)")
            st = hitl.list_open()[0]
            hitl.complete(st["id"], "스토어에서 환불 요청 제출 완료",
                          confirmation_no="RF-DEMO-001")
            print(f"  hitl-done {st['id']} → 케이스 자동 재개")
            case = cases_mod.load(case["id"])
            print(f"  케이스 상태: {case['status']}")
            _step("고객이 입금 확인 회신 → 추적 확정")
            _drop_mail(prof["contact"], prof["address"], "RE: 진행 안내",
                       "방금 환불 입금 확인했어요. 고마워요!", thread=fid)
            for r in mailbox.process_inbox():
                print(f"  {r['action']}: {r['detail']}")
            print(f"  track-run: {tracking.run_tick()}")
        else:
            _step("완료 추적 — 포털 재확인(egolite)으로 처리 완료 검증")
            print(f"  track-run: {tracking.run_tick()}")

    _step("결과 — 케이스·Flow·증빙")
    case = cases_mod.load(case["id"])
    print(f"  케이스 최종 상태: {case['status']}")
    print(f"  라운드 기록 {len(case['rounds'])}건:")
    for r in case["rounds"]:
        print(f"    · [{r['direction']}] {r['summary'][:70]}")
    print(f"  증빙 {len(case['evidence'])}건:")
    for e in case["evidence"]:
        print(f"    · {e['path']} — {e['note']}")
    print(f"  Flow 문서: {flow.flow_path(fid)}")
    print(f"  상태 메일(고객 스레드): {len(list(common.OUTBOX.glob('*.md')))}통 → {common.OUTBOX}")
    ok = case["status"] == "resolved"
    print("\n" + ("✅ 데모 성공 — 접수부터 입금 확인까지 전 과정 완료"
                  if ok else f"⚠ 데모 종료 — 최종 상태 {case['status']}"))
    return 0 if ok else 1
