"""스트레스 업무 플레이북 — 미루면 스트레스가 쌓이는 장기·감정소모형 업무의 유형 사전.

환불·분쟁·해지처럼 "한번 시작하면 오래 걸리고 감정이 소모되는" 일은
일반 위임과 달리 ① 우선 처리(멘탈 케어)되고 ② 케이스(core/cases.py)로
수명주기를 관리하며 ③ 요청 접수가 아니라 **결과 확인(입금 등)까지** 추적한다.

유형별 처리 채널:
  email  — 상대방과 이메일을 주고받으며 결과를 내는 협상형 (core/negotiation.py)
  portal — 해당 시스템(사이트)에 접속해 절차를 완료하는 실행형 (core/egolite.py)
  hybrid — 포털 접수 후 이메일 추적을 병행

공개 인터페이스:
  PLAYBOOKS: list[dict]
  detect(text) -> dict | None          # 텍스트에서 플레이북 매칭
  extract_intent(subject, body) -> dict  # 상대·금액·주문번호·목표 추출
  is_stress_kind(kind) -> bool         # 큐 kind가 스트레스 케이스인지
"""
from __future__ import annotations

import re

# 유형 사전 — demo/emails 100통의 10개 카테고리와 1:1 대응
PLAYBOOKS: list[dict] = [
    {"id": "refund-dispute",
     "baseline_minutes": 120, "emotion_load": 5,
     "evidence": "ops/research-time-baselines.md#스트레스 — S7·S9·S4·S5 (B)", "name": "구매·클래스 환불 분쟁 (이메일 협상)",
     "channel": "email", "max_rounds": 6, "tracking_days": 7,
     "triggers": ["환불 분쟁", "환불 요구", "환불해달라", "환불 거부", "클래스 환불", "공방 환불", "환불 협상"],
     "opener": "소비자분쟁해결기준에 따른 환불 요구",
     "escalation": "한국소비자원 1372 분쟁조정 신청 또는 카드사 이의제기"},
    {"id": "edu-refund",
     "baseline_minutes": 120, "emotion_load": 5,
     "evidence": "ops/research-time-baselines.md#스트레스 — S7 준용 (C+)", "name": "학원·인강 중도 해지 환불 (위약금 협상)",
     "channel": "email", "max_rounds": 6, "tracking_days": 7,
     "triggers": ["학원 환불", "인강 환불", "수강료 환불", "중도 해지 환불", "교습비 반환"],
     "opener": "학원법 제18조(교습비 반환 기준)에 따른 잔여분 환불 요구",
     "escalation": "교육청 민원 접수 및 한국소비자원 분쟁조정"},
    {"id": "subscription-refund",
     "baseline_minutes": 90, "emotion_load": 4,
     "evidence": "ops/research-time-baselines.md#스트레스 — S3 (B)", "name": "구독 해지 + 미사용분 환불 (포털)",
     "channel": "portal", "max_rounds": 3, "tracking_days": 5,
     "triggers": ["구독 환불", "구독 해지 환불", "미사용분 환불", "자동결제 환불", "OTT 환불"],
     "opener": "구독 해지 및 미사용 기간 일할 환불 신청",
     "escalation": "결제 카드사 이의제기"},
    {"id": "app-refund",
     "baseline_minutes": 60, "emotion_load": 4,
     "evidence": "ops/research-time-baselines.md#스트레스 — S3 준용 (C+)", "name": "인앱 결제·앱 환불 (스토어 포털)",
     "channel": "portal", "max_rounds": 3, "tracking_days": 3,
     "triggers": ["인앱 결제 환불", "앱 환불", "앱스토어 환불", "구글 환불", "실수 결제"],
     "opener": "스토어 환불 정책에 따른 결제 취소 신청",
     "escalation": "스토어 고객센터 수동 접수 (사람 개입)"},
    {"id": "telecom-dispute",
     "baseline_minutes": 90, "emotion_load": 4,
     "evidence": "ops/research-time-baselines.md#스트레스 — S9·S4 (B)", "name": "통신·요금 과오납 이의신청 (하이브리드)",
     "channel": "hybrid", "max_rounds": 5, "tracking_days": 14,
     "triggers": ["요금 이의신청", "부당 청구", "과오납", "요금 환불", "이중 청구"],
     "opener": "청구 내역 소명 요구 및 과오납분 환급 신청",
     "escalation": "통신분쟁조정위원회 조정 신청"},
    {"id": "delivery-refund",
     "baseline_minutes": 75, "emotion_load": 4,
     "evidence": "ops/research-time-baselines.md#스트레스 — S7 준용 (C+)", "name": "오배송·미배송 환불 (쇼핑몰 포털)",
     "channel": "portal", "max_rounds": 3, "tracking_days": 5,
     "triggers": ["오배송", "미배송 환불", "배송 안 옴", "파손 환불", "반품 환불"],
     "opener": "전자상거래법 제17조 청약철회에 따른 환불 접수",
     "escalation": "전자거래분쟁조정위원회 조정 신청"},
    {"id": "reservation-refund",
     "baseline_minutes": 90, "emotion_load": 5,
     "evidence": "ops/research-time-baselines.md#스트레스 — S7 준용 (C+)", "name": "예약 취소 수수료 분쟁 (이메일 협상)",
     "channel": "email", "max_rounds": 5, "tracking_days": 7,
     "triggers": ["예약 취소 환불", "취소 수수료", "숙소 환불", "위약금 환불", "노쇼 수수료"],
     "opener": "소비자분쟁해결기준(숙박업) 취소 시점별 환불 기준 요구",
     "escalation": "한국소비자원 1372 분쟁조정 신청"},
    {"id": "warranty-claim",
     "baseline_minutes": 90, "emotion_load": 4,
     "evidence": "ops/research-time-baselines.md#스트레스 — S4 (C+)", "name": "무상수리·교환 청구 (이메일 협상)",
     "channel": "email", "max_rounds": 5, "tracking_days": 10,
     "triggers": ["무상수리", "보증 수리", "교환 요구", "하자 보상", "품질보증"],
     "opener": "품질보증기준에 따른 무상수리 또는 교환 요구",
     "escalation": "한국소비자원 피해구제 신청"},
    {"id": "membership-cancel",
     "baseline_minutes": 75, "emotion_load": 5,
     "evidence": "ops/research-time-baselines.md#스트레스 — S3·S7 (B)", "name": "멤버십·헬스장 해지 환불 (포털)",
     "channel": "portal", "max_rounds": 4, "tracking_days": 7,
     "triggers": ["멤버십 해지 환불", "헬스장 환불", "회원권 환불", "이용권 환불", "해지 방어"],
     "opener": "방문판매법 제31조 계약 해지 및 잔여분 환불 신청",
     "escalation": "한국소비자원 분쟁조정 + 카드사 할부항변권"},
    {"id": "deposit-recovery",
     "baseline_minutes": 150, "emotion_load": 5,
     "evidence": "ops/research-time-baselines.md#스트레스 — S7·S4·S5 (B)", "name": "보증금·미수령 환급금 회수 (하이브리드)",
     "channel": "hybrid", "max_rounds": 5, "tracking_days": 14,
     "triggers": ["보증금 반환", "보증금 안 줌", "환급금 수령", "미수령 환급", "예치금 반환"],
     "opener": "보증금 반환 청구 — 근거 계약·영수 내역 첨부",
     "escalation": "내용증명 발송 및 지급명령 신청 안내"},
]

_BY_ID = {p["id"]: p for p in PLAYBOOKS}


def playbook(pid: str) -> dict | None:
    return _BY_ID.get(pid)


# 복합구 트리거가 하나도 안 맞을 때의 단일 키워드 폴백 — "환불이 2주째 안
# 들어와요"처럼 평범한 표현도 스트레스 유형으로 잡는다 (키워드 → 플레이북 id).
_KEYWORD_FALLBACK = [
    ("보증금", "deposit-recovery"), ("환급금", "deposit-recovery"),
    ("위약금", "reservation-refund"), ("취소 수수료", "reservation-refund"),
    ("해지", "membership-cancel"), ("무상수리", "warranty-claim"),
    ("하자", "warranty-claim"), ("과오납", "telecom-dispute"),
    ("미입금", "refund-dispute"), ("분쟁", "refund-dispute"),
    ("환불", "refund-dispute"),
]


def detect(text: str) -> dict | None:
    """텍스트에서 스트레스 플레이북 매칭 — 트리거 최다 일치 승.
    복합구 매칭이 없으면 단일 키워드 폴백(_KEYWORD_FALLBACK 순서 우선)."""
    low = (text or "").lower()
    best, best_score = None, 0
    for pb in PLAYBOOKS:
        score = sum(1 for t in pb["triggers"] if t.lower() in low)
        if score > best_score:
            best, best_score = pb, score
    if best is not None:
        return best
    by_id = {pb["id"]: pb for pb in PLAYBOOKS}
    for kw, pid in _KEYWORD_FALLBACK:
        if kw in low:
            return by_id.get(pid)
    return None


def is_stress_kind(kind: str) -> bool:
    return bool(kind) and kind.startswith("case:")


# ── 인텐트 추출 (메일 본문 → 구조화) ──────────────────────
_MERCHANT_MAIL = re.compile(
    r"(?:상대|업체|merchant|고객센터)\s*(?:이메일|메일)?\s*[:：]\s*([\w.+-]+@[\w.-]+)", re.I)
_QUOTED_FROM = re.compile(r">\s*(?:from|보낸사람|발신)\s*[:：]\s*.*?([\w.+-]+@[\w.-]+)", re.I)
_AMOUNT = re.compile(r"금액\s*[:：]\s*([\d,]+)")
_AMOUNT_WON = re.compile(r"([\d,]{4,})\s*원")
_ORDER_NO = re.compile(r"(주문|예약|계약|회원|결제|송장)번호\s*[:：]?\s*([A-Za-z0-9-]+)")
_MERCHANT_NAME = re.compile(r"업체(?:명)?\s*[:：]\s*(\S[^\n]*)")
_URL = re.compile(r"url\s*[:：]\s*(\S+)", re.I)


def extract_intent(subject: str, body: str) -> dict:
    """메일에서 케이스 인텐트 추출: 상대 이메일·업체명·금액·주문번호·포털 URL."""
    text = f"{subject}\n{body}"
    intent: dict = {"goal": "refund"}
    m = _MERCHANT_MAIL.search(text) or _QUOTED_FROM.search(text)
    if m:
        intent["merchant_email"] = m.group(1).lower()
    m = _MERCHANT_NAME.search(text)
    if m:
        intent["merchant"] = m.group(1).strip()
    elif intent.get("merchant_email"):
        intent["merchant"] = intent["merchant_email"].split("@")[1].split(".")[0]
    m = _AMOUNT.search(text) or _AMOUNT_WON.search(text)
    if m:
        intent["amount"] = int(m.group(1).replace(",", ""))
    m = _ORDER_NO.search(text)
    if m:
        intent["order_no"] = m.group(2)
    m = _URL.search(text)
    if m:
        intent["portal_url"] = m.group(1)
    return intent
