"""정책 — 범위 밖·고위험 요청 거절 (TC-DEL-007, UC-B7).

고위험 작업·차단 목록은 여기 단일 출처로 관리한다 (사람용 문서: ops/policy.md).
거절 시에도 Flow에 기록하고, 합법적·저위험 대안을 1개 제시한다.

공개 인터페이스:
  check(text) -> dict | None   # 차단이면 {"rule", "reason", "alternative"}
"""
from __future__ import annotations

BLOCKED = [
    {"rule": "타인 계정·사생활 접근",
     "triggers": ["타인 sns", "몰래 확인", "남의 계정", "타인 계정", "위치 추적", "몰래 보"],
     "reason": "타인의 계정·사생활에 접근하는 일은 수행하지 않아요.",
     "alternative": "본인 계정의 보안 점검이나 공개된 정보 조사는 도와드릴 수 있어요."},
    {"rule": "은행 이체·송금 대행",
     "triggers": ["계좌 이체해", "송금해줘", "이체 대행", "돈 보내줘"],
     "reason": "계좌 이체·송금은 고객 본인만 할 수 있는 고위험 금융 행위예요.",
     "alternative": "이체에 필요한 정보 정리와 납부 기한 알림은 대신해 드릴 수 있어요."},
    {"rule": "의약품·처방약 구매",
     "triggers": ["처방약 구매", "약 대신 사줘", "의약품 주문", "전문의약품"],
     "reason": "의약품 구매는 법적으로 본인 확인이 필요한 영역이라 대행하지 않아요.",
     "alternative": "비대면 진료 예약과 약국 위치·영업시간 확인은 도와드릴 수 있어요."},
    {"rule": "법적 효력 있는 약관·계약 동의 대행",
     "triggers": ["약관 동의해줘", "계약서 서명", "전자서명 대행", "동의 대행"],
     "reason": "법적 효력이 있는 동의·서명은 고객 본인이 직접 해야 해요.",
     "alternative": "약관·계약서의 핵심 조항 요약과 주의점 정리는 대신해 드릴 수 있어요."},
    {"rule": "시험·자격 부정행위",
     "triggers": ["시험 대신", "대리 시험", "과제 대신 제출"],
     "reason": "시험·평가의 대리 수행은 하지 않아요.",
     "alternative": "학습 일정 관리와 접수 기한 챙기기는 도와드릴 수 있어요."},
]


def check(text: str) -> dict | None:
    """차단 매칭 — 걸리면 규칙 dict, 아니면 None."""
    low = (text or "").lower()
    for rule in BLOCKED:
        if any(t in low for t in rule["triggers"]):
            return rule
    return None
