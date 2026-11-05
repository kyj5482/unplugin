"""community.py — 공통 위임 특성 기반 커뮤니티 v0 (피벗 2026-11-04).

당근이 '중고 거래'라는 공통 행동 위에 지역 커뮤니티를 세웠듯, 우리는
'같은 일을 에이전트에 위임한다'는 공통 특성 위에 커뮤니티를 세운다.
적립 이력(data/dividend/*/ledger.json)에서 고객별 상위 위임 유형을 뽑아
카테고리 그룹으로 자동 편성하고, 그룹 다이제스트(규모·합산 절약·익명 팁)를
보내며, 같은 그룹 + 같은 지역(profile.region)의 이웃이 있으면 무브먼트 제안에
"함께 움직이자"는 모임 섹션을 붙인다 — 온라인 절약이 오프라인 관계로 이어지는 지점.

익명 원칙: 메일에는 닉네임(이름 첫 글자 + 그룹 내 번호)만 쓴다.
상태 저장: data/community/groups.json (다이제스트 발송 시각 — 주 1회 중복 방지)
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from . import classify, common, dividend, notify

STRESS_GROUP = "환불·분쟁"
MIN_GROUP = 2            # 그룹 성립 최소 인원
DIGEST_DAYS = 7          # 다이제스트 최소 간격(일)

# 카테고리 → 그룹 이름 (사람이 모이고 싶은 이름으로)
GROUP_NAMES = {
    "쇼핑": "장보기 해방 클럽",
    "예약": "예약은 맡기는 사람들",
    "금융·청구": "청구서 제로 모임",
    "구독·계정": "구독 다이어트 클럽",
    "행정·민원": "민원 끝내기 모임",
    "교육·육아": "육아 행정 품앗이",
    "주거·생활": "집안일 오프로더",
    "건강": "건강 챙김 클럽",
    "이동·여행": "여행 준비 해방단",
    "정보·비교": "비교는 에이전트에게",
    "커뮤니케이션": "메일 제로 클럽",
    "중고·거래": "거래 품앗이",
    STRESS_GROUP: "환불 전사단",
}

# 그룹별 익명 공유 팁 한 줄 (v0 고정 문구 — 추후 실제 멤버 팁 수집으로 대체)
GROUP_TIPS = {
    "쇼핑": "정기 주문은 '재고 떨어지기 3일 전 자동 주문'까지 시키면 체감이 다릅니다.",
    "예약": "예약 요청에 '마감이면 대안 2개를 한 번에'를 붙이면 핑퐁이 사라져요.",
    "금융·청구": "'지난달보다 10% 오르면 알려줘' 조건을 달면 청구서를 아예 안 봐도 돼요.",
    "구독·계정": "해지 요청엔 '미사용분 일할 환불까지 확인'을 꼭 붙이세요.",
    "행정·민원": "민원은 '접수번호를 받아서 보고해줘'까지 시켜야 끝까지 갑니다.",
    "교육·육아": "가정통신문은 '매주 금요일 한 번에 요약'으로 모으면 평일이 조용해져요.",
    "주거·생활": "수리 접수는 '방문 일정 2개 중 선택지로 보고해줘'가 깔끔해요.",
    "건강": "검진 예약은 '공복 조건·주차까지 확인해서 보고'를 붙여보세요.",
    "이동·여행": "항공권은 '취소 수수료 조건을 요약해서 보고'까지 시키면 나중이 편해요.",
    "정보·비교": "비교 요청엔 '추천 1 + 대안 2 + 이유'를 틀로 주면 결정이 빨라져요.",
    "커뮤니케이션": "회신 대행보다 '회신 초안만 만들어 보고'가 처음엔 안전해요.",
    "중고·거래": "시세 조사를 먼저 시키고, 흥정 한도를 숫자로 정해 주세요.",
    STRESS_GROUP: "접수가 아니라 '입금 확인까지'를 명시하는 게 환불의 전부입니다.",
}


def _state_path() -> Path:
    return common.DATA / "community" / "groups.json"


def _load_state() -> dict:
    p = _state_path()
    return common.read_json(p) if p.exists() else {"groups": {}}


def _plugin_categories() -> dict[str, str]:
    return {pl["id"]: pl.get("category", "") for pl in classify.load_catalog()}


def group_of_event(event: dict, cat_map: dict[str, str]) -> str | None:
    """적립 이벤트 → 그룹 키(카테고리). 스트레스 유형은 전용 그룹."""
    pid = event.get("plugin") or ""
    if pid.startswith("stress:"):
        return STRESS_GROUP
    cat = cat_map.get(pid, "")
    return cat or None


def memberships() -> dict[str, list[dict]]:
    """전 고객 적립 이력 → {그룹: [{customer, events, minutes}]} (고객당 상위 2개 유형)."""
    cat_map = _plugin_categories()
    groups: dict[str, dict[str, dict]] = {}
    for cid in dividend.all_customers():
        ledger = dividend.load_ledger(cid)
        per_cat: dict[str, dict] = {}
        for e in ledger["events"]:
            g = group_of_event(e, cat_map)
            if not g:
                continue
            row = per_cat.setdefault(g, {"events": 0, "minutes": 0})
            row["events"] += 1
            row["minutes"] += e["saved_minutes"]
        top = sorted(per_cat.items(), key=lambda kv: -kv[1]["events"])[:2]
        for g, row in top:
            groups.setdefault(g, {})[cid] = {"customer": cid, **row}
    return {g: sorted(rows.values(), key=lambda r: r["customer"])
            for g, rows in groups.items()}


def nickname(cid: str, idx: int) -> str:
    """익명 닉네임 — 이름 첫 글자 + 그룹 내 번호 (메일에 실명·주소 노출 금지)."""
    prof = common.load_profiles().get(cid, {})
    first = (prof.get("name") or cid)[:1]
    return f"{first}{idx + 1}"


def _regions(members: list[dict]) -> dict[str, list[str]]:
    """그룹 멤버를 region 별로 묶는다 (region 없는 고객은 제외)."""
    profiles = common.load_profiles()
    by_region: dict[str, list[str]] = {}
    for m in members:
        region = profiles.get(m["customer"], {}).get("region")
        if region:
            by_region.setdefault(region, []).append(m["customer"])
    return by_region


def meetup_section(customer_id: str, ledger: dict | None = None) -> str:
    """무브먼트 제안 메일에 붙는 '같은 그룹 모임' 섹션 — 조건 미충족이면 빈 문자열.

    조건: 고객이 속한 그룹에 같은 region 멤버가 본인 포함 MIN_GROUP 이상.
    """
    prof = common.load_profiles().get(customer_id, {})
    region = prof.get("region")
    if not region:
        return ""
    lines: list[str] = []
    for g, members in memberships().items():
        ids = [m["customer"] for m in members]
        if customer_id not in ids:
            continue
        same = _regions(members).get(region, [])
        if customer_id not in same or len(same) < MIN_GROUP:
            continue
        others = len(same) - 1
        lines.append(f"- **{GROUP_NAMES.get(g, g)}** — {region}에 같은 일을 "
                     f"맡기는 이웃이 {others}명 더 있어요. 이번 무브먼트, "
                     "같이 움직여볼까요? 회신 주시면 자리를 만들어 드려요.")
    if not lines:
        return ""
    return "🧑‍🤝‍🧑 같은 그룹 모임 제안\n" + "\n".join(lines)


def _digest_body(g: str, members: list[dict], week_minutes: int) -> str:
    names = ", ".join(nickname(m["customer"], i) for i, m in enumerate(members))
    h, mm = divmod(week_minutes, 60)
    return "\n".join([
        f"'{GROUP_NAMES.get(g, g)}' 멤버가 {len(members)}명이 됐어요 ({names}).",
        f"그룹이 함께 벌어둔 시간: {h}시간 {mm}분.",
        "",
        f"이번 주 그룹 팁 — {GROUP_TIPS.get(g, '팁 카드의 [보고] 한 줄을 잊지 마세요.')}",
        "",
        "같은 일을 맡기는 사람들이라 통하는 게 많아요. 나누고 싶은 팁이 있으면 "
        "회신해 주세요 — 익명으로 다음 다이제스트에 실어 드려요.",
    ])


def run_tick(force: bool = False) -> list[dict]:
    """커뮤니티 1틱 — 그룹 다이제스트 발송 (그룹당 DIGEST_DAYS 에 1회).

    반환: [{group, members, sent}] — sent 는 이번 틱에 발송했는지.
    """
    common.ensure_dirs()
    state = _load_state()
    results = []
    now = common.now()
    for g, members in memberships().items():
        if len(members) < MIN_GROUP:
            results.append({"group": g, "members": len(members), "sent": False,
                            "detail": "인원 미달"})
            continue
        last = state["groups"].get(g, {}).get("last_digest")
        if last and not force:
            if now - common.datetime.fromisoformat(last) < timedelta(days=DIGEST_DAYS):
                results.append({"group": g, "members": len(members), "sent": False,
                                "detail": "주기 미도래"})
                continue
        minutes = sum(m["minutes"] for m in members)
        body = _digest_body(g, members, minutes)
        for m in members:
            notify.send(m["customer"], f"{GROUP_NAMES.get(g, g)} — 이번 주 다이제스트",
                        body, thread=f"community-{common.slug(g)}")
        state["groups"][g] = {"last_digest": common.iso(now), "members": len(members)}
        results.append({"group": g, "members": len(members), "sent": True,
                        "detail": f"다이제스트 {len(members)}통"})
    common.write_json(_state_path(), state)
    return results


def status_text() -> str:
    """CLI용 그룹 현황."""
    groups = memberships()
    if not groups:
        return "아직 커뮤니티 그룹이 없어요 — 적립이 쌓이면 자동으로 편성됩니다."
    profiles = common.load_profiles()
    lines = ["커뮤니티 그룹 현황 (같은 일을 위임하는 사람들):"]
    for g, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        regions = _regions(members)
        rtxt = " · ".join(f"{r} {len(v)}명" for r, v in sorted(regions.items())) or "지역 미등록"
        mark = "" if len(members) >= MIN_GROUP else " (인원 미달)"
        lines.append(f"  · {GROUP_NAMES.get(g, g)} [{g}] — {len(members)}명{mark} | {rtxt}")
        for i, m in enumerate(members):
            region = profiles.get(m["customer"], {}).get("region", "-")
            lines.append(f"      {nickname(m['customer'], i)} ({m['customer']}) "
                         f"적립 {m['events']}건 {m['minutes']}분 · {region}")
    return "\n".join(lines)
