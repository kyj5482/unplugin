"""오프라인 전환 — 위임 완료 후 개인화 추천·거절 학습·예약 연결·재문진 (TC-OFF-001~004).

위임이 완료되어 시간이 확보되면:
  ① 확보 시간 추정치가 Flow에 기록되고
  ② 타입 축(M/R·P/A)·시간·프로필 제약에 맞는 오프라인 경험 1~3개를 근거와 함께 추천
  ③ 소비형보다 체험·배움형을 우선한다 (departments/product/experiences.json)

거절(TC-OFF-002): 사유에서 제약을 추출해 프로필에 누적하고, 같은 추천을 반복하지
않으며, 제약을 반영한 대안을 재추천한다.
수락(TC-OFF-003): 같은 Flow에서 예약 위임으로 전환 — "위임→추천→예약"이 한 Flow에 이어진다.
재문진(TC-OFF-004): 2주 후 스크린타임 변화 + 실측 reclaimed_hours를 피드백 파일로
저장하고, 추정 대비 차이를 상품기획으로 핸드오프한다.

공개 인터페이스:
  maybe_recommend(flow_id, customer_id, reclaimed_hours) -> list[dict]
  reject(customer_id, flow_id, reason) -> list[dict]      # 재추천 결과
  accept(customer_id, flow_id) -> str | None              # 예약 큐 아이템 id
  resurvey(customer_id, data, feedback_dir=None) -> Path  # 피드백 파일 경로
"""
from __future__ import annotations

import json
from pathlib import Path

from . import common, flow, notify

EXPERIENCES_PATH = common.ROOT / "departments" / "product" / "experiences.json"
_KIND_ORDER = {"체험": 0, "배움": 0, "소비": 1}  # 체험·배움 우선

# 거절 사유 → 프로필 제약 매핑
_CONSTRAINT_RULES = [
    (("멀", "머니까", "머네", "거리", "이동"), {"max_distance_km": 5, "label": "이동 거리 부담"}),
    (("비싸", "비용", "가격"), {"max_cost": "low", "label": "비용 부담"}),
    (("시간이 없", "짧게", "바빠"), {"max_hours": 1.5, "label": "시간 여유 부족"}),
    (("사람", "혼자", "북적"), {"social": "A", "label": "혼자 하는 활동 선호"}),
]


def _load_experiences() -> list[dict]:
    return json.loads(EXPERIENCES_PATH.read_text(encoding="utf-8"))["experiences"]


def _profile_path(customer_id: str) -> Path:
    return common.CUSTOMERS / customer_id / "profile.json"


def _pick(profile: dict, hours: float, exclude: set[str]) -> list[dict]:
    tcode = str(profile.get("type", "SFRA")).upper()
    axis, social = (tcode[2], tcode[3]) if len(tcode) == 4 else ("R", "A")
    constraints = profile.get("constraints", {})
    out = []
    for e in _load_experiences():
        if e["title"] in exclude:
            continue
        if e["hours"] > max(hours, 1.0) + 0.5:
            continue
        if constraints.get("max_distance_km") is not None \
                and e["distance_km"] > constraints["max_distance_km"]:
            continue
        if constraints.get("max_hours") is not None and e["hours"] > constraints["max_hours"]:
            continue
        if constraints.get("social") and e["social"] != constraints["social"]:
            continue
        score = (0 if e["axis"] == axis else 1,
                 0 if e["social"] == social else 1,
                 _KIND_ORDER.get(e["kind"], 1))
        out.append((score, e))
    out.sort(key=lambda t: t[0])
    return [e for _, e in out[:3]]


def _reason(e: dict, profile: dict, hours: float) -> str:
    tcode = str(profile.get("type", "")).upper()
    return (f"확보된 약 {hours:g}시간 안에 가능({e['hours']:g}h), "
            f"타입 {tcode}의 {e['axis']}축·{e['social']}축에 부합, "
            f"{e['kind']}형 — {e['desc']}")


def maybe_recommend(flow_id: str, customer_id: str,
                    reclaimed_hours: float) -> list[dict]:
    """위임 완료 직후 추천 (TC-OFF-001). 추천 이력은 프로필에 누적된다."""
    ppath = _profile_path(customer_id)
    if not ppath.exists() or reclaimed_hours <= 0:
        return []
    profile = common.read_json(ppath)
    exclude = set(profile.get("suggested_history", []))
    picks = _pick(profile, reclaimed_hours, exclude)
    if not picks:
        return []
    lines = [f"- **{e['title']}** — {_reason(e, profile, reclaimed_hours)}" for e in picks]
    flow.add_step(flow_id, "product",
                  f"확보 시간 약 {reclaimed_hours:g}h → 오프라인 추천 {len(picks)}건: "
                  + ", ".join(e["title"] for e in picks),
                  notify_customer=False)
    notify.send_flow_update(
        customer_id, flow_id, flow.flow_path(flow_id), "완료",
        f"비워진 {reclaimed_hours:g}시간, 화면 밖에서 이렇게 써보세요",
        "\n".join(lines) + "\n\n마음에 드는 걸 \"수락: <이름>\"으로, 안 맞으면 \"거절: <이유>\"로 회신해 주세요.")
    profile["suggested_history"] = sorted(exclude | {e["title"] for e in picks})
    common.write_json(ppath, profile)
    return picks


def reject(customer_id: str, flow_id: str, reason: str) -> list[dict]:
    """추천 거절 — 사유에서 제약 추출·프로필 누적 + 같은 추천 없이 재추천 (TC-OFF-002)."""
    ppath = _profile_path(customer_id)
    profile = common.read_json(ppath)
    constraints = profile.setdefault("constraints", {})
    label = "기타"
    for keys, update in _CONSTRAINT_RULES:
        if any(k in reason for k in keys):
            label = update["label"]
            constraints.update({k: v for k, v in update.items() if k != "label"})
            break
    labels = profile.setdefault("constraint_labels", [])
    if label not in labels:
        labels.append(label)
    common.write_json(ppath, profile)
    flow.add_step(flow_id, "cs",
                  f"추천 거절 접수 — 사유 \"{reason[:60]}\" → 프로필 제약 추가({label}). "
                  "제약 반영 대안 재추천",
                  handoff="cs → product: 거절 사유 반영한 추천 로직 개선 소재",
                  notify_customer=False)
    # 재추천 — 이전 추천(suggested_history)은 다시 등장하지 않는다
    hours = float(constraints.get("max_hours") or 2.0)
    picks = _pick(profile, hours, set(profile.get("suggested_history", [])))
    if picks:
        lines = [f"- **{e['title']}** — {_reason(e, profile, hours)}" for e in picks]
        notify.send_flow_update(
            customer_id, flow_id, flow.flow_path(flow_id), "진행 중",
            "말씀 주신 점을 반영해 다시 골랐어요",
            f"\"{reason[:40]}\" 말씀을 프로필에 기억해 둘게요.\n" + "\n".join(lines))
        profile["suggested_history"] = sorted(
            set(profile.get("suggested_history", [])) | {e["title"] for e in picks})
        common.write_json(ppath, profile)
    return picks


def accept(customer_id: str, flow_id: str, title: str = "") -> str | None:
    """추천 수락 → 같은 Flow에서 예약 위임으로 전환 (TC-OFF-003)."""
    from . import queue
    name = title.strip() or "수락한 오프라인 경험"
    flow.add_step(flow_id, "concierge",
                  f"추천 수락 → 예약 위임으로 전환: {name} "
                  "(위임→추천→예약이 이 Flow 하나에 이어집니다)",
                  notify_customer=False)
    return queue.enqueue(customer_id, "plugin:activity-class-booking",
                         f"{name} 예약", flow_id)


def resurvey(customer_id: str, data: dict, feedback_dir=None) -> Path:
    """2주 후 재문진 (TC-OFF-004) — 실측 피드백 파일 저장 + 상품기획 핸드오프.

    data: {screen_before_h, screen_after_h, offline_realized, offline_story,
           delegation, satisfaction, estimate_h}
    """
    from . import kpi
    fdir = Path(feedback_dir) if feedback_dir else kpi.DEFAULT_FEEDBACK_DIR
    fdir.mkdir(parents=True, exist_ok=True)
    before = float(data.get("screen_before_h", 0))
    after = float(data.get("screen_after_h", 0))
    measured = round(max(before - after, 0.0), 1)
    estimate = float(data.get("estimate_h", 0))
    diff = round(measured - estimate, 1)
    path = fdir / f"{common.ts()}-{customer_id}-resurvey.md"
    path.write_text("\n".join([
        "---",
        f"customer: {customer_id}",
        f"delegation: {data.get('delegation', '재문진')}",
        f"satisfaction: {data.get('satisfaction', 4)}",
        f"offline_realized: {data.get('offline_realized', '미확인')}",
        f"offline_story: {data.get('offline_story', '')}",
        f"delegated_hours: {estimate:g}",
        f"reclaimed_hours: {measured:g}   # 실측 (스크린타임 {before:g}h → {after:g}h)",
        f"screen_before_h: {before:g}",
        f"screen_after_h: {after:g}",
        f"estimate_vs_actual: {diff:+g}",
        "---",
        "",
        f"2주 재문진 — 스크린타임 변화 {before:g}h → {after:g}h (실측 reclaimed {measured:g}h, "
        f"추정 대비 {diff:+g}h)",
    ]), encoding="utf-8")
    fid = flow.create_flow(customer_id, f"2주 재문진: {customer_id}", "재문진",
                           f"스크린타임 {before:g}h → {after:g}h, 실측 reclaimed {measured:g}h")
    flow.add_step(fid, "cs",
                  f"재문진 완료 — 실측 {measured:g}h vs 추정 {estimate:g}h ({diff:+g}h)",
                  handoff=f"cs → product: 추정 대비 실측 차이 {diff:+g}h 반영한 추천·추정 보정",
                  notify_customer=False)
    flow.set_status(fid, "완료")
    return path
