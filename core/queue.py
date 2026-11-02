"""티어 슬롯 기반 파일 큐 — TC-OPS-003/004/006/007, TC-DEL-005.

상태 디렉토리: data/queue/pending|active|done|cancelled (common.py 계약).
- 고객 티어별 동시 슬롯(common.TIER_SLOTS) 안에서 pending→active FIFO 승격
- active 실행은 v0 시뮬레이션: 결제 승인 게이트(approval.gate) 4분기
- 대기 타임아웃: deadline 경과 pending에 지연 통지 1회 (아이템 유지)
- 사용량: done 이동 시 data/usage/<customer>.json 월별 est_hours 누적,
  티어 한도 80% 도달 시 사전 통지 1회 (TC-OPS-006)
"""
from __future__ import annotations

from . import approval, common, flow, notify

# 월 위임 시간 한도 (ops/pricing.md: One ~10h / Flow ~40h / Life 무제한급)
TIER_HOURS = {"one": 10.0, "flow": 40.0, "life": 999.0}
USAGE_DIR = common.DATA / "usage"


# ── enqueue ──────────────────────────────────────────────

def enqueue(customer_id: str, kind: str, summary: str, flow_id: str,
            amount: int = 0, est_hours: float = 0.0) -> str:
    """pending에 아이템 생성. 슬롯이 없어 대기면 대기 순번·예상을 1회 안내."""
    common.ensure_dirs()
    created = common.now()
    item_id = f"{created.strftime('%Y%m%d-%H%M%S-%f')}-{customer_id}-{common.slug(summary, 24)}"
    item = {
        "id": item_id,
        "customer": customer_id,
        "created": created.isoformat(),  # 마이크로초 포함 → 같은 초에도 FIFO 보장
        "kind": kind,
        "summary": summary,
        "flow": flow_id,
        "amount": amount,
        "est_hours": est_hours,
        "approved": None,
        "asked": False,              # 승인 질문 1회 플래그 (재질문 금지)
        "notified_hold": False,      # 승인 무응답 보류 통지 1회 플래그
        "notified_timeout": False,   # 대기 타임아웃 통지 1회 플래그
        "charged": None,             # done=True / cancelled=False (미차감)
        "deadline": common.default_deadline(),
    }
    common.write_json(common.queue_item_path("pending", item_id), item)
    _maybe_send_wait_notice(item)
    return item_id


def _maybe_send_wait_notice(item: dict) -> None:
    prof = common.load_profiles().get(item["customer"])
    if not prof:
        return
    slots = common.TIER_SLOTS.get(prof.get("tier", "one"), 1)
    active_cnt = sum(1 for i in common.list_queue("active")
                     if i["customer"] == item["customer"])
    ahead_pending = sum(1 for i in common.list_queue("pending")
                        if i["customer"] == item["customer"]
                        and i["created"] < item["created"])
    ahead = active_cnt + ahead_pending
    if ahead < slots:
        return  # 바로 다음 틱에 착수 가능 → 대기 안내 불필요
    rank = ahead - slots + 1
    lines = [
        f"\"{item['summary']}\" 요청을 접수했어요.",
        f"지금 진행 중인 일이 있어 대기열에 올려두었어요. 대기 순번: {rank}번째.",
        f"늦어도 {item['deadline']} 전에는 시작될 예정이고, 슬롯이 비는 대로 바로 착수해 이 스레드로 알려드릴게요.",
    ]
    if prof.get("tier") == "one":
        # 상위 티어 안내는 강요 없이 딱 1문장 1회 (TC-OPS-003)
        lines.append("참고로, Unplug Flow 티어에서는 동시에 2건까지 대기 없이 진행돼요 — 원하실 때만 살펴보세요.")
    notify.send(item["customer"],
                f"대기 안내: {item['summary']} (대기 {rank}번째)",
                "\n".join(lines), thread=item["flow"])


# ── 한 틱 처리 ────────────────────────────────────────────

def run_tick() -> dict:
    """한 번의 틱: 슬롯 승격 → active 실행 → 대기 타임아웃 점검."""
    common.ensure_dirs()
    profiles = common.load_profiles()
    stats = {"promoted": 0, "executed": 0, "waiting": 0, "timeouts": 0}

    # 1. 고객별 티어 슬롯 내 pending→active FIFO 승격 (created 순서 보장)
    active_cnt: dict[str, int] = {}
    for it in common.list_queue("active"):
        active_cnt[it["customer"]] = active_cnt.get(it["customer"], 0) + 1
    for it in common.list_queue("pending"):  # created 오름차순
        prof = profiles.get(it["customer"], {})
        slots = common.TIER_SLOTS.get(prof.get("tier", "one"), 1)
        if active_cnt.get(it["customer"], 0) < slots:
            common.move_queue_item(it, "pending", "active")
            active_cnt[it["customer"]] = active_cnt.get(it["customer"], 0) + 1
            stats["promoted"] += 1

    # 2. active 실행 (v0 시뮬레이션)
    for it in common.list_queue("active"):
        _execute(it, profiles.get(it["customer"], {}), stats)

    # 3. 대기 타임아웃: deadline 지난 pending → 지연 통지 1회, 아이템 유지
    now_iso = common.iso()
    for it in common.list_queue("pending"):
        stats["waiting"] += 1
        if it["deadline"] < now_iso and not it.get("notified_timeout"):
            new_eta = common.default_deadline()
            notify.send(
                it["customer"],
                f"대기 지연 안내: {it['summary']}",
                "\n".join([
                    f"\"{it['summary']}\" 요청이 예상보다 오래 대기하고 있어요. 죄송해요.",
                    "지연 사유: 앞선 위임 건의 처리가 예상보다 길어지고 있어요.",
                    f"새 예상 시작 시점: 늦어도 {new_eta} 전.",
                    "계속 대기하시려면 회신 없이 그대로 두시면 되고, 취소를 원하시면 이 메일에 \"취소\"라고 회신해 주세요.",
                    "취소하셔도 위임 시간(사용량)은 전혀 차감되지 않아요.",
                ]),
                thread=it["flow"])
            it["notified_timeout"] = True
            common.write_json(common.queue_item_path("pending", it["id"]), it)
            stats["timeouts"] += 1
    return stats


def _execute(it: dict, prof: dict, stats: dict) -> None:
    fid = it["flow"]
    if it.get("approved") is True:
        # 고객이 명시적으로 승인 → 결제 진행 후 완료
        flow.add_step(fid, "it",
                      f"고객 승인 확인 — 결제 진행: {it['summary']} / {it['amount']}원")
        _finish(it, prof, f"결제 완료: {it['summary']} / {it['amount']}원 (고객 승인 후 진행)")
        stats["executed"] += 1
        return
    if it.get("approved") is False:
        # 고객 거부 → 결제 없이 안전 종결, 사용량 미차감
        it["charged"] = False
        common.move_queue_item(it, "active", "cancelled")
        flow.cancel(fid, "고객이 결제 승인을 거부하셔서 결제 없이 안전하게 종결했어요. (사용량 미차감)")
        stats["executed"] += 1
        return
    if it["amount"] > 0:
        verdict = approval.gate(prof, it["amount"], it)
        if verdict == "proceed":
            flow.add_step(fid, "it",
                          f"결제 직전 내역 요약: {it['summary']} / {it['amount']}원 (한도 이내 자동 진행)")
            _finish(it, prof, f"결제 완료: {it['summary']} / {it['amount']}원 (한도 이내 자동 진행)")
            stats["executed"] += 1
            return
        # need_approval
        if not it.get("asked"):
            flow.ask_customer(fid, (
                f"결제 승인이 필요해요. 금액: {it['amount']}원 "
                f"(사전 승인 한도 {prof.get('approval_limit', 0)}원 초과) / "
                f"내용: {it['summary']} / "
                "승인 방법: 이 메일에 \"승인\" 또는 \"거부\"라고 회신해 주세요."))
            it["asked"] = True  # 재질문 금지
            common.write_json(common.queue_item_path("active", it["id"]), it)
        elif it["deadline"] < common.iso() and not it.get("notified_hold"):
            # 승인 무응답 타임아웃 → 결제하지 않고 보류 통지 1회, 아이템 유지
            flow.add_step(fid, "it", (
                f"승인 응답 대기 타임아웃 — 결제하지 않고 보류 중이에요: "
                f"{it['summary']} / {it['amount']}원. \"승인\" 회신 주시면 바로 재개할게요."))
            it["notified_hold"] = True
            common.write_json(common.queue_item_path("active", it["id"]), it)
            stats["timeouts"] += 1
        stats["waiting"] += 1
        return
    # amount == 0 → 바로 실행·완료
    flow.add_step(fid, "it", f"실행 요약: {it['summary']} 처리 완료")
    _finish(it, prof, f"완료: {it['summary']}")
    stats["executed"] += 1


def _finish(it: dict, prof: dict, summary: str) -> None:
    """done 이동 + flow 완결 + 사용량 차감."""
    it["charged"] = True
    common.move_queue_item(it, "active", "done")
    est = float(it.get("est_hours") or 0.0)
    flow.complete(it["flow"], summary, reclaimed_hours=est if est > 0 else None)
    _charge_usage(it["customer"], est, prof)


# ── 취소 / 승인·거부 ──────────────────────────────────────

def cancel(item_id: str, by_customer: bool = True) -> dict | None:
    """pending/active 어디서든 cancelled로 이동. 사용량 미차감(charged=False)."""
    for state in ("pending", "active"):
        p = common.queue_item_path(state, item_id)
        if p.exists():
            it = common.read_json(p)
            it["charged"] = False  # 미차감 기록
            common.move_queue_item(it, state, "cancelled")
            who = "고객 요청으로" if by_customer else "운영 판단으로"
            flow.cancel(it["flow"], f"{who} 취소했어요. 위임 시간(사용량)은 차감되지 않아요.")
            return it
    return None


def _set_approved(item_id: str, value: bool) -> dict | None:
    for state in ("active", "pending"):
        p = common.queue_item_path(state, item_id)
        if p.exists():
            it = common.read_json(p)
            it["approved"] = value
            common.write_json(p, it)
            return it
    return None


def approve(item_id: str) -> dict | None:
    """고객 승인 기록 — 다음 tick에서 결제 진행 후 done."""
    return _set_approved(item_id, True)


def reject(item_id: str) -> dict | None:
    """고객 거부 기록 — 다음 tick에서 결제 없이 cancelled."""
    return _set_approved(item_id, False)


# ── 사용량 (월별 est_hours 누적, 80% 사전 통지) ───────────

def usage_path(customer_id: str):
    return USAGE_DIR / f"{customer_id}.json"


def _charge_usage(customer_id: str, hours: float, prof: dict) -> None:
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    p = usage_path(customer_id)
    data = common.read_json(p) if p.exists() else {"monthly": {}, "notified_months": []}
    month = common.now().strftime("%Y-%m")
    used = round(data["monthly"].get(month, 0.0) + hours, 3)
    data["monthly"][month] = used
    limit = TIER_HOURS.get(prof.get("tier", "one"), 10.0)
    if used >= 0.8 * limit and month not in data["notified_months"]:
        remaining = max(round(limit - used, 1), 0)
        notify.send(customer_id, "이번 달 위임 시간 한도 80% 도달 안내", "\n".join([
            f"이번 달 위임 시간이 티어 한도의 80%에 도달했어요. (사용 {used}h / 한도 {limit}h, 잔여 약 {remaining}h)",
            "한도를 넘길 것 같으면 두 가지 중 고르실 수 있어요:",
            "1) 다음 달 초기화까지 신규 위임을 대기열에 두기",
            "2) 상위 티어로 업그레이드해 한도를 늘리기",
            "참고: 위임 수행 시간만 차감되고, 문진·명확화 대화는 차감되지 않아요.",
        ]))
        data["notified_months"].append(month)
    common.write_json(p, data)
