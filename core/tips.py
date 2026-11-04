"""tips.py — 위임 팁 엔진 v0 (피벗 2026-11-04 · ops/pivot-2026-11-04.md).

이메일을 연결해 일을 대신 처리하지 않는다. 대신 "이 일은 Muze 같은 에이전트에
이렇게 요청하면 약 N분 절약" 팁 카드를 만든다. 모든 팁의 프롬프트에는
**보고 한 줄**("끝나면 <전용주소>로 제목에 [보고]를 붙여 완료 보고 메일")이
항상 포함된다 — 사용자가 그대로 실행하면 보고 메일이 도착하고,
core/dividend.py 가 자동으로 적립한다. 팁 → 실행 → 보고 → 적립의 닫힌 루프.

스트레스 유형(환불·분쟁 등)은 고급 팁: 접수가 아니라 입금(결과) 확인까지
시키는 법 — 재촉·에스컬레이션 지시를 프롬프트에 포함한다 (core/stress.py).
"""
from __future__ import annotations

from pathlib import Path

from . import classify, common, flow, notify, stress
from .dividend import DEFAULT_BASELINE, DEFAULT_EMOTION, emotion_dots

REPORT_LINE = ("일이 다 끝나면 {addr} 로 제목 맨 앞에 [보고]를 붙여 "
               "무엇을 어떻게 처리했는지 완료 보고 메일을 보내줘.")
PLACEHOLDER_ADDR = "<내 전용주소>"


def _report_line(customer: dict | None) -> str:
    addr = (customer or {}).get("address") or PLACEHOLDER_ADDR
    return REPORT_LINE.format(addr=addr)


def make_tip(text: str, customer: dict | None = None) -> dict:
    """업무 텍스트 → 팁 카드. 미매칭이면 범용 팁(보고 한 줄은 항상 포함)."""
    text = (text or "").strip()
    report_line = _report_line(customer)
    gist = " ".join(text.split())[:80] or "이 일"
    hit = classify.match(text)
    pb = stress.detect(text)
    pl = hit["plugin"] if hit else None

    if pb:  # 고급 팁 — 끝까지(입금 확인까지) 시키는 법
        minutes = max(int((pl or {}).get("baseline_minutes", 120)), 120)
        emotion = max(int((pl or {}).get("emotion_load", 4)), 4)
        prompt = (f"{gist} — {pb['opener']}. "
                  "접수만 하고 끝내지 말고 실제 입금(결과) 확인까지 진행해줘. "
                  "상대가 회신하지 않으면 2회까지 재촉하고, 그래도 안 되면 "
                  f"{pb['escalation']} 단계로 넘어가 줘. "
                  f"진행 상황이 바뀔 때마다 알려줘. {report_line}")
        return {"task": pb["name"], "plugin_id": (pl or {}).get("id") or f"stress:{pb['id']}",
                "matched": True, "stress": True, "saved_minutes_est": minutes,
                "emotion_load": emotion, "muze_prompt": prompt}

    if pl:
        minutes = int(pl.get("baseline_minutes", DEFAULT_BASELINE))
        emotion = int(pl.get("emotion_load", DEFAULT_EMOTION))
        prompt = (f"{gist} — 필요한 조건(예산·기한·선호)을 먼저 확인하고 진행해줘. "
                  "결제나 확정이 필요한 지점에서는 진행 전에 물어봐줘. "
                  f"{report_line}")
        return {"task": pl["name"], "plugin_id": pl["id"], "matched": True,
                "stress": False, "saved_minutes_est": minutes,
                "emotion_load": emotion, "muze_prompt": prompt}

    prompt = (f"{gist} — 단계를 나눠 진행하고, 애매한 지점은 임의로 정하지 말고 "
              f"물어봐줘. {report_line}")
    return {"task": gist, "plugin_id": None, "matched": False, "stress": False,
            "saved_minutes_est": DEFAULT_BASELINE, "emotion_load": DEFAULT_EMOTION,
            "muze_prompt": prompt}


def card_body(card: dict) -> str:
    """팁 카드 → 고객 메일 본문."""
    lines = [
        "이 일은 직접 맡아드리는 대신, 쓰고 계신 AI 에이전트(Muze 등)에 "
        "이렇게 시켜보세요:",
        "",
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
        card["muze_prompt"],
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄",
        "",
        f"- 예상 절약: 약 {card['saved_minutes_est']}분 (직접 하실 때 기준)",
        f"- 아끼는 감정: {emotion_dots(card['emotion_load'])}",
    ]
    if card.get("stress"):
        lines.append("- 이런 일은 '접수'가 아니라 '입금 확인'까지 시키는 게 핵심이에요 — "
                     "위 프롬프트에 그 지시가 들어 있어요.")
    lines.append("- 마지막 [보고] 한 줄은 꼭 그대로 두세요 — 보고 메일이 도착하는 순간 "
                 "절약 시간이 자동으로 적립됩니다. 직접 기록하실 건 없어요.")
    return "\n".join(lines)


def send_card(customer_id: str, card: dict, thread: str = "") -> Path | None:
    """팁 카드를 고객 메일로 발송 (CLI·수동 발송용)."""
    return notify.send(customer_id,
                       f"위임 팁: {card['task']} · 약 {card['saved_minutes_est']}분 절약",
                       card_body(card), thread=thread)


def reply_with_tip(path: Path, mail: dict, customer: dict,
                   fid: str, title: str, task_text: str) -> dict:
    """mailbox 분기 — 포워딩 업무 메일에 대행 접수 대신 팁 카드 회신 (피벗 기본값)."""
    card = make_tip(task_text, customer)
    flow.add_step(
        fid, "concierge",
        f"위임 팁 카드 회신 — '{card['task']}' (예상 절약 {card['saved_minutes_est']}분, "
        f"감정 {card['emotion_load']}). 대행 접수 없음 — 피벗(2026-11-04) 기본 동작",
        notify_customer=False)
    notify.send_flow_update(
        customer["id"], fid, flow.flow_path(fid), "완료",
        f"\"{title}\" — 직접 해드리는 대신, 더 좋은 방법을 알려드려요",
        card_body(card))
    flow.set_status(fid, "완료")
    path.unlink()
    kind = card.get("plugin_id") or "범용"
    return {"mail": path.name, "action": "tip_sent",
            "detail": f"팁 카드 회신 — flow {fid} / {kind} / "
                      f"예상 절약 {card['saved_minutes_est']}분"}
