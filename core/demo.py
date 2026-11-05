"""데모 러너 — 피벗 여정(기본) + 레거시 스트레스 100통(--legacy) 단계별 시연.

`python3 -m core demo-run <n>` 은 demo/runtime/ 격리 환경(서브프로세스 +
UNPLUGIN_DATA/FLOWS 오버라이드)에서 실행되므로 실데이터·flows/를 오염시키지
않는다. 각 단계가 번호와 함께 출력된다.

피벗 여정(기본, demo/index.json journeys 1~5 — 고객 1명씩):
  이웃 적립(배경) → 포워딩→팁 카드 회신 → 보고 수신→자동 적립(산정 근거)
  → 임계치→무브먼트 제안(+동네 모임 섹션) → 커뮤니티 다이제스트 → Admin 생성
레거시(--legacy, demo/legacy/ 100통): 동결된 대행 경로 재생 — 접수→협상/포털→입금 확인.
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
LEGACY_DIR = DEMO_DIR / "legacy"
RUNTIME = DEMO_DIR / "runtime"


def _manifest() -> dict:
    return json.loads((DEMO_DIR / "index.json").read_text(encoding="utf-8"))


def _legacy_index() -> list[dict]:
    return json.loads((LEGACY_DIR / "index.json").read_text(encoding="utf-8"))["emails"]


def list_demos() -> None:
    man = _manifest()
    print(f"피벗 데모 여정 {len(man['journeys'])}건 (메일 {len(man['emails'])}통) — "
          "실행: python3 -m core demo-run <번호>\n")
    for j in man["journeys"]:
        print(f"  {j['n']}. {j['title']} — 보정 ×{j['time_factor']:g} · {j['situation']}")
    print("\n레거시 스트레스 데모 100통(동결 경로): "
          "python3 -m core demo-run <1~100> --legacy")


def run(n: int, fresh: bool = False, legacy: bool = False) -> int:
    """격리 환경 서브프로세스로 demo-exec 실행 (common 경로 상수 재적용을 위해)."""
    if fresh and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    env = dict(os.environ)
    env["UNPLUGIN_DATA"] = str(RUNTIME / "data")
    env["UNPLUGIN_FLOWS"] = str(RUNTIME / "flows")
    env["UNPLUGIN_REPORTS"] = str(RUNTIME / "reports")
    cmd = [sys.executable, "-m", "core", "demo-exec", str(n)]
    if legacy:
        # 레거시 100통은 동결된 대행 경로의 재생이다 (피벗 전 시나리오)
        env["UNPLUGIN_LEGACY_DELEGATION"] = "1"
        cmd.append("--legacy")
    else:
        env.pop("UNPLUGIN_LEGACY_DELEGATION", None)  # 피벗 기본 모드
    return subprocess.call(cmd, env=env, cwd=str(common.ROOT))


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


def _install_customer(cid: str) -> dict:
    """demo/customers/<cid> 프로필을 격리 환경에 설치."""
    src = DEMO_DIR / "customers" / cid
    dst = common.CUSTOMERS / cid
    if not dst.exists():
        shutil.copytree(src, dst)
    return common.read_json(dst / "profile.json")


def _feed_inbox(files: list[str]) -> None:
    for f in files:
        src = DEMO_DIR / f
        (common.INBOX / src.name).write_text(src.read_text(encoding="utf-8"),
                                             encoding="utf-8")


def _print_mail(p: Path, max_lines: int = 9) -> None:
    m = common.parse_mail(p)
    print(f"  ✉ → {m['to']} | {m['subject']}")
    for line in m["body"].splitlines()[:max_lines]:
        print(f"    {line}")


def exec_scenario(n: int, legacy: bool = False) -> int:
    if legacy:
        return _exec_legacy(n)
    return _exec_journey(n)


def _exec_journey(n: int) -> int:
    """피벗 여정 — 팁→실행(외부)→보고→적립→무브먼트→커뮤니티→Admin."""
    from . import admin, community, dividend, mailbox
    man = _manifest()
    entry = next((j for j in man["journeys"] if j["n"] == n), None)
    if entry is None:
        print(f"여정 {n}번 없음 (1~{len(man['journeys'])})")
        return 1
    cid = entry["customer"]
    mails = [e for e in man["emails"] if e["customer"] == cid]
    reports = [e for e in mails if e["kind"] == "report"][:5]
    unmatched = [e for e in mails if e["kind"] == "unmatched"][:1]
    forward = [e for e in mails if e["kind"] == "forward"][:1]
    neighbor = next((j["customer"] for j in man["journeys"]
                     if j["region"] == entry["region"] and j["customer"] != cid), None)

    common.ensure_dirs()
    prof = _install_customer(cid)
    print("=" * 60)
    print(f"피벗 데모 {n}: {entry['title']}")
    print(f"고객 {entry['name']} ({cid}) · 지역 {entry['region']} · "
          f"개인 보정 ×{entry['time_factor']:g} · 전용주소 {prof['address']}")
    print(f"격리 환경: {common.DATA}")
    print("=" * 60)

    if neighbor:
        _step(f"배경 — 같은 동네({entry['region']}) 이웃 '{neighbor}'도 쓰고 있다 (적립 2건)")
        _install_customer(neighbor)
        nb = [e for e in man["emails"]
              if e["customer"] == neighbor and e["kind"] == "report"][:2]
        _feed_inbox([e["file"] for e in nb])
        for r in mailbox.process_inbox():
            print(f"  {r['action']}: {r['detail']}")

    _step("고객이 귀찮은 일을 전용 주소로 포워딩 → 대행 접수 대신 '팁 카드' 회신")
    _feed_inbox([e["file"] for e in forward])
    for r in mailbox.process_inbox():
        print(f"  {r['action']}: {r['detail']}")
    tip_mails = sorted(common.OUTBOX.glob("*.md"))
    if tip_mails:
        _print_mail(tip_mails[-1], max_lines=12)

    _step(f"에이전트 완료 보고 수신 → 자동 적립 (보고 {len(reports)}통 + 미매칭 1통)")
    _feed_inbox([e["file"] for e in reports + unmatched])
    before = len(sorted(common.OUTBOX.glob("*.md")))
    for r in mailbox.process_inbox():
        print(f"  {r['action']}: {r['detail']}")
    for p in sorted(common.OUTBOX.glob("*.md"))[before:before + 2]:
        _print_mail(p)

    _step("시간 배당 잔고 — 수동 기록 0건으로 쌓인 숫자")
    print(dividend.summary(cid))

    _step("임계치 도달 → 무브먼트 제안 (같은 그룹 동네 모임 섹션 포함)")
    moves = [p for p in sorted(common.OUTBOX.glob("*.md"))
             if "무브먼트" in common.parse_mail(p)["subject"]]
    if moves:
        _print_mail(moves[-1], max_lines=14)
    else:
        print("  (임계치 미도달 — 제안 없음)")

    _step("커뮤니티 1틱 — 같은 일을 위임하는 그룹 다이제스트")
    for r in community.run_tick(force=True):
        mark = "발송" if r["sent"] else "건너뜀"
        print(f"  · {r['group']} ({r['members']}명) — {mark}: {r['detail']}")

    _step("Admin 운영판 생성")
    path = admin.generate()
    print(f"  {path}")

    led = dividend.load_ledger(cid)
    ok = (led["totals"]["events_count"] >= len(reports)
          and bool(moves) and path.exists())
    print("\n" + ("✅ 데모 성공 — 팁→보고→적립→무브먼트→커뮤니티→Admin 전 과정 완료"
                  if ok else "⚠ 데모 종료 — 일부 단계 미충족"))
    return 0 if ok else 1


def _exec_legacy(n: int) -> int:
    from . import cases as cases_mod, flow, hitl, mailbox, queue, tracking
    entry = next((e for e in _legacy_index() if e["n"] == n), None)
    if entry is None:
        print(f"데모 {n}번 없음 (1~{len(_legacy_index())})")
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
    mail_text = (LEGACY_DIR / entry["file"]).read_text(encoding="utf-8")
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
