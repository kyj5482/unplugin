"""`python3 -m core <cmd>` — Unplugin v0 운영 CLI.

mailbox/queue/onboarding/kpi 는 다른 에이전트가 병행 개발 중이므로
반드시 함수 안에서 지연 임포트하고, 없으면 안내만 하고 종료한다.
"""
from __future__ import annotations

import argparse
import re
import sys
from importlib import import_module

from . import common


def _optional(module: str, func: str):
    """core.<module>.<func> 지연 로드. 준비 전이면 None + 안내 출력."""
    try:
        mod = import_module(f".{module}", package=__package__)
    except ImportError:
        print(f"[준비 중] core/{module}.py 모듈이 아직 없어요. "
              f"다른 부문에서 개발 중입니다 — 준비되면 이 명령이 바로 동작합니다.")
        return None
    fn = getattr(mod, func, None)
    if fn is None:
        print(f"[준비 중] core.{module}.{func}() 함수가 아직 없어요. "
              f"모듈은 있지만 해당 기능이 미구현입니다.")
        return None
    return fn


# ── 명령 핸들러 ──────────────────────────────────────────

def cmd_dashboard(_args) -> int:
    from . import dashboard
    path = dashboard.generate()
    print(f"대시보드 생성 완료: {path}")
    return 0


def cmd_mail_poll(_args) -> int:
    fn = _optional("mailbox", "process_inbox")
    if fn is None:
        return 0
    result = fn()
    if result is not None:
        print(result)
    return 0


def cmd_queue_run(_args) -> int:
    fn = _optional("queue", "run_tick")
    if fn is None:
        return 0
    result = fn()
    if result is not None:
        print(result)
    return 0


def _decide(action: str, item_id: str) -> int:
    fn = _optional("queue", action)
    if fn is None:
        return 0
    result = fn(item_id)
    label = "승인" if action == "approve" else "반려"
    if result is None:
        print(f"{label} 실패: 큐에서 '{item_id}' 아이템을 찾지 못했어요. "
              f"`python3 -m core status`로 큐 상태를 확인해 보세요.")
        return 1
    print(f"{label} 처리: {item_id} → {result}")
    return 0


def cmd_approve(args) -> int:
    return _decide("approve", args.item_id)


def cmd_reject(args) -> int:
    return _decide("reject", args.item_id)


def cmd_onboard(args) -> int:
    fn = _optional("onboarding", "create_profile")
    if fn is None:
        return 0
    result = fn(args.json_path)
    if result is not None:
        print(result)
    return 0


def cmd_kpi(_args) -> int:
    fn = _optional("kpi", "aggregate")
    if fn is None:
        return 0
    result = fn()
    if result is not None:
        print(result)
    return 0


def cmd_serve(args) -> int:
    from . import service
    return service.run(interval=args.interval, once=args.once)


def cmd_mail_fetch(_args) -> int:
    fn = _optional("mail_io", "fetch_new")
    if fn is None:
        return 0
    result = fn()
    if result is not None:
        print(f"수신: {result}")
    return 0


def cmd_mail_send(args) -> int:
    fn = _optional("mail_io", "send_pending")
    if fn is None:
        return 0
    result = fn(dry_run=args.dry_run)
    if result is not None:
        label = "발신 대상(dry-run)" if args.dry_run else "발신"
        print(f"{label}: {result}")
    return 0


def _recent_flows(limit: int = 5) -> list[tuple[str, str, str]]:
    """(파일 stem, 제목, 상태) 최신순 — common 경로만 사용해 직접 파싱."""
    if not common.FLOWS.exists():
        return []
    paths = [p for p in common.FLOWS.glob("*.md")
             if p.name not in ("_template.md", "README.md")]
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in paths[:limit]:
        text = p.read_text(encoding="utf-8")
        tm = re.search(r"^# Flow: (.+)$", text, re.M)
        sm = re.search(r"\*\*상태\*\*:\s*(.+)", text)
        out.append((p.stem,
                    tm.group(1).strip() if tm else p.stem,
                    sm.group(1).strip() if sm else "?"))
    return out


def cmd_status(_args) -> int:
    profiles = common.load_profiles()
    print(f"고객 프로필: {len(profiles)}명")

    parts = []
    for state in common.QUEUE_STATES:
        d = common.QUEUE / state
        n = len(list(d.glob("*.json"))) if d.exists() else 0
        parts.append(f"{state} {n}")
    print("큐: " + " · ".join(parts))

    n_out = len(list(common.OUTBOX.glob("*.md"))) if common.OUTBOX.exists() else 0
    print(f"outbox(발신): {n_out}통")

    recent = _recent_flows(5)
    if recent:
        print("최근 Flow:")
        for stem, title, status in recent:
            print(f"  - [{status}] {title} ({stem})")
    else:
        print("최근 Flow: 없음")
    return 0


# ── 파서 ────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m core",
        description="Unplugin v0 운영 CLI — 로컬·파일 기반·stdlib only")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<cmd>")

    sub.add_parser("dashboard", help="data/dashboard.html 생성 (대표용 Unified View)"
                   ).set_defaults(fn=cmd_dashboard)
    sub.add_parser("mail-poll", help="data/inbox/ 처리 (수신 시뮬레이션)"
                   ).set_defaults(fn=cmd_mail_poll)
    sub.add_parser("queue-run", help="큐 1틱 처리 (슬롯 배분·타임아웃 점검)"
                   ).set_defaults(fn=cmd_queue_run)

    ap = sub.add_parser("approve", help="큐 아이템 승인")
    ap.add_argument("item_id", help="큐 아이템 ID")
    ap.set_defaults(fn=cmd_approve)

    rj = sub.add_parser("reject", help="큐 아이템 반려")
    rj.add_argument("item_id", help="큐 아이템 ID")
    rj.set_defaults(fn=cmd_reject)

    ob = sub.add_parser("onboard", help="고객 프로필 생성 (온보딩 JSON)")
    ob.add_argument("json_path", help="온보딩 입력 JSON 파일 경로")
    ob.set_defaults(fn=cmd_onboard)

    sv = sub.add_parser(
        "serve", help="서비스 데몬 — 수신→처리→큐→발신→대시보드 사이클 반복")
    sv.add_argument("--interval", type=int, default=60,
                    help="사이클 간격(초, 기본 60)")
    sv.add_argument("--once", action="store_true",
                    help="1사이클만 실행 후 종료")
    sv.set_defaults(fn=cmd_serve)

    sub.add_parser("mail-fetch", help="IMAP 실수신 1회 (v0.5 — mail_io)"
                   ).set_defaults(fn=cmd_mail_fetch)

    ms = sub.add_parser("mail-send", help="outbox 실발신 (v0.5 — mail_io)")
    ms.add_argument("--dry-run", action="store_true",
                    help="실발신 없이 발신 대상만 확인")
    ms.set_defaults(fn=cmd_mail_send)

    sub.add_parser("kpi", help="주간 KPI 리포트 생성").set_defaults(fn=cmd_kpi)
    sub.add_parser("status", help="프로필·큐·outbox·최근 Flow 요약"
                   ).set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
