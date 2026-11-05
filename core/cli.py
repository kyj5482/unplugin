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


def cmd_tips(args) -> int:
    """위임 팁 카드 — "이 일은 에이전트에 이렇게 시키면 N분 절약" (피벗 2026-11-04)."""
    from . import tips as tips_mod
    customer = common.load_profiles().get(args.customer) if args.customer else None
    if args.customer and customer is None:
        print(f"고객 '{args.customer}' 프로필이 없어요.")
        return 1
    card = tips_mod.make_tip(args.text, customer)
    mark = " (유형 미매칭 — 범용 팁)" if not card["matched"] else (
        " (스트레스 유형 — 고급 팁)" if card["stress"] else "")
    print(f"업무: {card['task']}{mark}")
    print(f"예상 절약: 약 {card['saved_minutes_est']}분 · 감정 부하 {card['emotion_load']}/5")
    print(f"\n에이전트(Muze 등)에 이렇게 시키세요:\n  {card['muze_prompt']}")
    if customer:
        p = tips_mod.send_card(args.customer, card)
        print(f"\n팁 카드 메일 발송 → {p}")
    return 0


def cmd_dividend(args) -> int:
    """시간 배당 잔고 — 보고 메일로만 자동 적립, 수동 입력 없음."""
    from . import dividend
    ids = [args.customer] if args.customer else dividend.all_customers()
    if not ids:
        print("아직 적립된 잔고가 없어요 — 팁 카드의 [보고] 한 줄이 적립의 시작입니다.")
        return 0
    for cid in ids:
        print(dividend.summary(cid))
    return 0


def cmd_admin(_args) -> int:
    """피벗 운영판 — 잔고·보고 피드·무브먼트·팁·커뮤니티·미매칭 백로그."""
    from . import admin
    path = admin.generate()
    print(f"Admin 대시보드 생성: {path}")
    return 0


def cmd_calibrate(args) -> int:
    """고객 개인 보정 계수(time_factor) 조정 — 0.5~2.0 클램프."""
    from . import admin
    try:
        prof = admin.calibrate(args.customer, args.factor)
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f"{prof['id']} time_factor = ×{prof['time_factor']:g} — "
          "다음 적립부터 적용 (기준치 × 보정)")
    return 0


def cmd_community(_args) -> int:
    """커뮤니티 그룹 현황 — 같은 일을 위임하는 사람들."""
    from . import community
    print(community.status_text())
    return 0


def cmd_community_run(args) -> int:
    """커뮤니티 1틱 — 그룹 다이제스트 발송 (주 1회, --force 로 즉시)."""
    from . import community
    for r in community.run_tick(force=args.force):
        mark = "발송" if r["sent"] else "건너뜀"
        print(f"  · {r['group']} ({r['members']}명) — {mark}: {r['detail']}")
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


def cmd_directive(args) -> int:
    from . import directive
    r = directive.handle(args.text)
    print(f"담당 부문: {r['dept']}")
    print(f"산출물: {r['output']}")
    print(f"Flow: {r['flow']}")
    print(r["check"])
    print(r["next"])
    return 0


def cmd_agents(_args) -> int:
    from . import agents
    load = agents.workload()
    print("AI 에이전트 직원 현황:")
    for a in agents.roster():
        print(f"  {a['name']}({a['id']}) · {a['role']:<11} · 진행 중 {load.get(a['id'], 0)}건 — {a['desc']}")
    return 0


def cmd_cases(_args) -> int:
    from . import cases
    rows = cases.list_cases()
    if not rows:
        print("케이스 없음")
        return 0
    for c in rows:
        amt = c["intent"].get("amount")
        print(f"[{c['status']:<17}] {c['id']} · {c['type']} · "
              f"{c['intent'].get('merchant', '?')}{f' · {amt:,}원' if amt else ''} "
              f"· 라운드 {len(c['rounds'])} · 담당 {c.get('assignee')}")
    return 0


def cmd_hitl_list(_args) -> int:
    from . import hitl
    rows = hitl.list_open()
    if not rows:
        print("대기 중인 사람 개입 없음")
        return 0
    for st in rows:
        print(f"{st['id']} · {st['kind']} · {st['reason']} "
              f"(가이드: data/handoff/{st['id']}.md)")
    return 0


def cmd_hitl_done(args) -> int:
    from . import hitl
    st = hitl.complete(args.handoff_id, args.note, args.confirmation or "")
    if st is None:
        print(f"처리 실패: 열린 핸드오프 '{args.handoff_id}'를 찾지 못했어요. "
              "`python3 -m core hitl-list`로 확인하세요.")
        return 1
    print(f"완료 보고 접수: {args.handoff_id} — 케이스/아이템이 자동 재개되었어요.")
    return 0


def cmd_track_run(_args) -> int:
    from . import tracking
    print(tracking.run_tick())
    return 0


def cmd_resurvey(args) -> int:
    import json as _json
    from . import recommend
    data = _json.loads(open(args.json_path, encoding="utf-8").read())
    path = recommend.resurvey(args.customer, data)
    print(f"재문진 피드백 저장: {path}")
    return 0


def cmd_demo_list(_args) -> int:
    from . import demo
    demo.list_demos()
    return 0


def cmd_demo_run(args) -> int:
    from . import demo
    return demo.run(args.n, fresh=args.fresh, legacy=args.legacy)


def cmd_demo_exec(args) -> int:
    from . import demo
    return demo.exec_scenario(args.n, legacy=args.legacy)


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

    tp = sub.add_parser("tips", help="위임 팁 카드 — 에이전트에 시키는 법 + 예상 절약 (피벗)")
    tp.add_argument("text", help="업무 내용 (예: \"공방 클래스 환불 분쟁 해결\")")
    tp.add_argument("--customer", default="", help="고객 id — 지정 시 팁 카드 메일 발송")
    tp.set_defaults(fn=cmd_tips)

    sub.add_parser("admin", help="피벗 운영판 생성 — data/admin.html (잔고·보고·커뮤니티)"
                   ).set_defaults(fn=cmd_admin)

    cb = sub.add_parser("calibrate", help="고객 개인 보정 계수(time_factor) 조정")
    cb.add_argument("customer")
    cb.add_argument("factor", type=float)
    cb.set_defaults(fn=cmd_calibrate)

    sub.add_parser("community", help="커뮤니티 그룹 현황 (공통 위임 특성 기반)"
                   ).set_defaults(fn=cmd_community)

    cr = sub.add_parser("community-run", help="커뮤니티 1틱 — 그룹 다이제스트 발송")
    cr.add_argument("--force", action="store_true", help="주기 무시하고 즉시 발송")
    cr.set_defaults(fn=cmd_community_run)

    dv = sub.add_parser("dividend", help="시간 배당 잔고 — 자동 적립 현황 (피벗)")
    dv.add_argument("--customer", default="", help="고객 id (생략 시 전체)")
    dv.set_defaults(fn=cmd_dividend)
    sub.add_parser("status", help="프로필·큐·outbox·최근 Flow 요약"
                   ).set_defaults(fn=cmd_status)

    dr = sub.add_parser("directive", help="대표 지시 처리 — \"지시: ...\"")
    dr.add_argument("text", help="지시 텍스트")
    dr.set_defaults(fn=cmd_directive)

    sub.add_parser("agents", help="AI 에이전트 직원 로스터·부하 현황"
                   ).set_defaults(fn=cmd_agents)
    sub.add_parser("cases", help="스트레스 케이스(환불·분쟁) 목록"
                   ).set_defaults(fn=cmd_cases)
    sub.add_parser("track-run", help="완료 추적 1틱 (확정→완결 / 기한 초과→넛지)"
                   ).set_defaults(fn=cmd_track_run)
    sub.add_parser("hitl-list", help="사람 개입 대기 목록"
                   ).set_defaults(fn=cmd_hitl_list)

    hd = sub.add_parser("hitl-done", help="사람 개입 완료 보고 → 자동 재개")
    hd.add_argument("handoff_id")
    hd.add_argument("--note", required=True, help="처리 내용")
    hd.add_argument("--confirmation", default="", help="접수번호 (있으면)")
    hd.set_defaults(fn=cmd_hitl_done)

    rs = sub.add_parser("resurvey", help="2주 재문진 결과 기록 (실측 Reclaimed)")
    rs.add_argument("customer")
    rs.add_argument("json_path")
    rs.set_defaults(fn=cmd_resurvey)

    sub.add_parser("demo-list", help="데모 시나리오(100통) 목록"
                   ).set_defaults(fn=cmd_demo_list)

    dm = sub.add_parser("demo-run", help="데모 1건을 격리 환경에서 단계별 실행")
    dm.add_argument("n", type=int, help="피벗 여정 번호(1~5) 또는 --legacy 와 1~100")
    dm.add_argument("--fresh", action="store_true", help="demo/runtime 초기화 후 실행")
    dm.add_argument("--legacy", action="store_true",
                    help="레거시 스트레스 100통(동결 대행 경로) 재생")
    dm.set_defaults(fn=cmd_demo_run)

    dx = sub.add_parser("demo-exec", help="(내부용) 격리 env 안에서 데모 실행")
    dx.add_argument("n", type=int)
    dx.add_argument("--legacy", action="store_true")
    dx.set_defaults(fn=cmd_demo_exec)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
