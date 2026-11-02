"""결제 승인 게이트 — TC-DEL-005.

한도 판정만 담당한다. 승인/거부/타임아웃 기록은 queue가 아이템 필드
(approved, asked, notified_hold)로 관리한다.
"""
from __future__ import annotations


def gate(profile: dict, amount: int, item: dict) -> str:
    """사전 승인 한도 판정.

    amount <= profile["approval_limit"] → "proceed" (결제 직전 요약 후 자동 진행)
    그 외 → "need_approval" (명시적 고객 승인 필요)
    """
    limit = int(profile.get("approval_limit", 0) or 0)
    return "proceed" if amount <= limit else "need_approval"
