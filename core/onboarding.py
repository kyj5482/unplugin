"""온보딩 — 프로필 생성·전용 주소 발급·금지 필터·오프라인 추천 근거.

커버 TC: ONB-001(첫 위임 1개), ONB-003(금지 목록 존중, UC-A3),
ONB-004(일괄 위임 → 한 가지로 축소, UC-A4), ONB-005(타입 축 근거 인용, UC-A5).

공개 인터페이스:
  create_profile(data) -> dict   # 프로필 저장 + 온보딩 Flow + 환영 메일
  check_deny(profile, task_text) -> bool
  suggest_offline(profile) -> dict  # {"title", "reason"} — reason에 타입 축 근거 명시
"""
from __future__ import annotations

import itertools
import secrets

from . import common, flow, notify

# 언플러그 타입 16개: S/T + F/C + M/R + P/A (ops/survey.md 단일 소스)
VALID_TYPES = {"".join(c) for c in itertools.product("ST", "FC", "MR", "PA")}

# 3·4번째 축(M/R × P/A) 조합별 오프라인 추천 — TC-ONB-005: 근거에 타입 축 인용
_OFFLINE_SUGGESTIONS = {
    ("M", "P"): {"title": "함께 배우는 도자기 원데이 클래스",
                 "reason": "M축(만들기·배움)·P축(함께) 기준 — 손으로 만들며 사람들과 어울리는 경험"},
    ("M", "A"): {"title": "혼자 몰입하는 목공 소품 만들기",
                 "reason": "M축(만들기·배움)·A축(혼자) 기준 — 조용히 몰입해 무언가를 완성하는 경험"},
    ("R", "P"): {"title": "친구와 느긋한 공원 피크닉",
                 "reason": "R축(쉼·감각)·P축(함께) 기준 — 편안한 자리에서 함께 쉬는 경험"},
    ("R", "A"): {"title": "혼자 걷는 가까운 숲길 산책",
                 "reason": "R축(쉼·감각)·A축(혼자) 기준 — 감각을 열고 혼자 충전하는 경험"},
}


def _validate(data: dict) -> None:
    for key in ("name", "contact", "type", "tier", "approval_limit", "deny_list", "first_delegation"):
        if key not in data:
            raise ValueError(f"필수 항목 누락: {key}")

    tcode = str(data["type"]).upper()
    if tcode not in VALID_TYPES:
        raise ValueError(f"타입 코드 오류: {data['type']} — S/T+F/C+M/R+P/A 조합 16개 중 하나여야 합니다")

    limit = data["approval_limit"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"approval_limit은 양의 정수여야 합니다: {limit!r}")

    first = data["first_delegation"]
    if isinstance(first, (list, tuple, set)):
        # UC-A4 / TC-ONB-004: 과도한 일괄 위임은 한 가지로 축소 — 신뢰는 한 단계씩
        raise ValueError("한 번에 한 가지만 위임할 수 있어요 (UC-A4) — 첫 위임은 하나를 고르고, "
                         "나머지는 대기 위임 후보로 남겨 주세요")
    if not isinstance(first, str) or not first.strip():
        raise ValueError("first_delegation은 비어 있지 않은 문자열 1개여야 합니다")

    deny_list = data["deny_list"]
    if not isinstance(deny_list, list):
        raise ValueError("deny_list는 리스트여야 합니다")
    for item in deny_list:
        if item and (item in first or first in item):
            # UC-A3 / TC-ONB-003: 금지 목록에 있는 일은 첫 위임이 될 수 없다
            raise ValueError(f"첫 위임 \"{first}\"이(가) 위임 금지 목록(\"{item}\")과 충돌합니다 (UC-A3)")


def _unique_id(base: str) -> str:
    cid, i = base, 1
    while (common.CUSTOMERS / cid).exists():
        i += 1
        cid = f"{base}-{i}"
    return cid


def create_profile(data: dict) -> dict:
    """온보딩 확인 결과로 프로필 생성 + 전용 주소 발급 + 온보딩 Flow + 환영 메일."""
    _validate(data)
    common.ensure_dirs()

    base = common.slug(data.get("roman") or data["name"])
    cid = _unique_id(base)
    # 주소 추측 방지: 이름 슬러그에 난수 토큰을 붙여 발급 (ops/email-channel.md)
    address = f"{cid}.{secrets.token_hex(2)}@unplugin.me"

    profile = {
        "id": cid,
        "name": data["name"],
        "address": address,
        "contact": data["contact"],
        "type": str(data["type"]).upper(),
        "tier": data["tier"],
        "approval_limit": data["approval_limit"],
        "deny_list": list(data["deny_list"]),
        "first_delegation": data["first_delegation"],
        "onboarded": True,
    }
    if data.get("time_value") is not None:
        profile["time_value"] = data["time_value"]
    if data.get("trusted_senders"):
        profile["trusted_senders"] = list(data["trusted_senders"])
    # UC-A4: 고객이 여러 가지를 한꺼번에 맡기려 하면 첫 위임 1개 + 나머지는 대기 후보로 기록
    if data.get("waiting_candidates"):
        profile["waiting_candidates"] = [str(w) for w in data["waiting_candidates"]
                                         if str(w) != data["first_delegation"]]

    cdir = common.CUSTOMERS / cid
    common.write_json(cdir / "profile.json", profile)
    common.write_json(cdir / "rules.json", {"rules": []})

    # 온보딩 Flow 생성 + 단계 기록 (프로필 저장 후 — 상태 메일이 연락처를 찾을 수 있도록)
    fid = flow.create_flow(cid, f"온보딩: {profile['name']}", "onboarding",
                           f"신규 고객 온보딩 — 타입 {profile['type']}, 첫 위임 \"{profile['first_delegation']}\"")
    flow.add_step(fid, "cs", f"프로필 생성·전용 주소 발급 ({address})", notify_customer=False)
    flow.add_step(fid, "cs", f"첫 위임 확정: {profile['first_delegation']} (한 번에 한 가지 원칙)",
                  notify_customer=False)
    if profile.get("waiting_candidates"):
        flow.add_step(fid, "cs",
                      f"대기 위임 후보 기록: {', '.join(profile['waiting_candidates'])} (UC-A4 축소 안내)",
                      notify_customer=False)
    profile["onboarding_flow"] = fid
    common.write_json(cdir / "profile.json", profile)

    # 환영 메일: 발급 주소 + 첫 위임 안내 + 사용법("포워딩만 하면 된다")
    notify.send(cid, f"환영합니다, {profile['name']}님 — 전용 주소가 발급되었어요", "\n".join([
        f"🔌 {profile['name']}님, Unplugin에 오신 것을 환영해요.",
        "",
        f"전용 주소가 발급되었어요: **{address}**",
        "",
        f"첫 위임은 \"{profile['first_delegation']}\"로 시작할게요. "
        "한 번에 한 가지씩, 신뢰를 한 단계씩 쌓아가요.",
        "",
        f"사용법은 간단해요. 맡기고 싶은 메일이 오면 {address}로 포워딩만 하면 됩니다. "
        "나머지는 저희가 처리하고, 진행 상황은 같은 스레드로 알려드려요.",
        "",
        f"승인 한도 {profile['approval_limit']:,}원까지는 묻지 않고 진행하고, "
        "그 이상은 꼭 먼저 여쭤볼게요.",
    ]), thread=fid)

    return profile


def check_deny(profile: dict, task_text: str) -> bool:
    """위임 금지 필터 (UC-A3): deny_list 항목이 task_text에 부분일치하면 True(위임 금지)."""
    text = (task_text or "").strip()
    return any(item and item in text for item in profile.get("deny_list", []))


def suggest_offline(profile: dict) -> dict:
    """타입 코드의 M/R·P/A 축 기반 오프라인 추천 — reason에 타입 축 근거 포함 (TC-ONB-005)."""
    tcode = str(profile.get("type", "")).upper()
    if tcode not in VALID_TYPES:
        raise ValueError(f"프로필 타입 코드 오류: {profile.get('type')!r}")
    pick = _OFFLINE_SUGGESTIONS[(tcode[2], tcode[3])]
    return {"title": pick["title"],
            "reason": f"{pick['reason']} (타입 {tcode}, ops/survey.md 축 정의)"}
