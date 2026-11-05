#!/usr/bin/env python3
"""데모 이메일 100통 생성기 — 10개 스트레스 유형 × 10통.

사용: python3 demo/generate_emails.py
산출: demo/emails/NNN-<type>.md (100통) + demo/index.json (매니페스트)

메일은 core/common.py 포맷(--- 헤더 ---)이며, 수신 주소는 data/customers/demo/
프로필의 전용 주소다. 본문에는 각 유형 플레이북(core/stress.py)의 트리거가
포함되어 분류기가 올바른 케이스로 접수한다. 결정적(난수 없음) — 재실행해도 동일.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from core import common  # noqa: E402

DEMO_DIR = ROOT / "demo" / "legacy"
EMAILS = DEMO_DIR / "emails"

PROFILE = json.loads((ROOT / "data/customers/demo/profile.json").read_text(encoding="utf-8"))
TO = PROFILE["address"]
FROM = PROFILE["contact"]

# 유형별 시나리오 — (업체, 상대 이메일 또는 url, 금액, 주문번호, 상황 한 줄)
SCENARIOS = {
    "refund-dispute": {
        "channel": "email",
        "instruction": "환불 거부당했는데 환불 요구 계속 주고받으면서 끝까지 받아줘. 환불 분쟁 해결 부탁해.",
        "title": "{merchant} 환불 분쟁",
        "items": [
            ("달빛공방", "cs@dalbit.example", 89000, "CL-2026-0412", "원데이 클래스 당일 취소했는데 전액 몰수래"),
            ("한강쿠킹스튜디오", "help@hancook.example", 120000, "CK-7781", "강사 사정으로 휴강됐는데 환불을 미뤄"),
            ("숲속목공방", "woodwork@soop.example", 95000, "WD-3302", "재료 불량으로 수업을 못 들었어"),
            ("미드나잇베이킹", "refund@midbake.example", 78000, "BK-5520", "2회권 샀는데 1회만 듣고 환불 거부당함"),
            ("어반플라워랩", "contact@uflower.example", 66000, "FL-1189", "클래스 일정이 일방적으로 변경됐어"),
            ("세라믹하우스", "hello@cerahouse.example", 110000, "CR-9015", "예약금 환불 규정이 계약과 달라"),
            ("패브릭아틀리에", "cs@fabricat.example", 84000, "FB-2297", "강좌 폐강됐는데 환불 대신 포인트만 준대"),
            ("글라스스튜디오", "info@glasswork.example", 132000, "GL-6633", "안전 문제로 수업 중단, 잔여분 환불 요구"),
            ("키친클래스301", "support@kc301.example", 99000, "KC-4410", "더블부킹으로 수업을 못 들었어"),
            ("보태니컬가든", "garden@botani.example", 72000, "BT-8842", "우천 취소인데 수수료를 떼겠대"),
        ],
    },
    "edu-refund": {
        "channel": "email",
        "instruction": "학원 환불 받아줘. 중도 해지 환불 기준대로 수강료 환불 요구하고 결과까지 확인해줘.",
        "title": "{merchant} 수강료 환불",
        "items": [
            ("코드스쿨아카데미", "admin@codeschool.example", 450000, "EDU-1101", "3개월 중 2주 듣고 그만뒀어"),
            ("리딩영어학원", "cs@readingenglish.example", 380000, "EDU-2202", "강사가 바뀌어서 그만두려고"),
            ("수학의정석학원", "office@mathjs.example", 420000, "EDU-3303", "이사 때문에 더 못 다녀"),
            ("키즈발레스튜디오", "ballet@kidsb.example", 280000, "EDU-4404", "아이가 다쳐서 진단서 있어"),
            ("온라인인강패스", "help@lecturepass.example", 199000, "EDU-5505", "연간 패스인데 3강만 들었어"),
            ("피아노포르테", "piano@forte.example", 320000, "EDU-6606", "레슨 시간이 계속 일방 변경돼"),
            ("드로잉클래스온", "draw@classon.example", 150000, "EDU-7707", "교재비 포함 환불 기준이 이상해"),
            ("스피치랩", "speech@lab.example", 360000, "EDU-8808", "환불 신청했는데 위약금 50%를 요구해"),
            ("코딩키즈캠프", "camp@codingkids.example", 540000, "EDU-9909", "캠프 일정이 취소됐는데 환불이 없어"),
            ("일본어마스터", "jp@master.example", 270000, "EDU-1010", "레벨이 안 맞아 첫 주에 그만뒀어"),
        ],
    },
    "subscription-refund": {
        "channel": "portal",
        "instruction": "이 구독 해지하고 미사용분 환불까지 받아줘. 구독 환불 처리 결과 알려줘.",
        "title": "{merchant} 구독 해지·환불",
        "items": [
            ("넷플릭스", "url: https://netflix.com/account", 17000, "SUB-0001", "두 달째 안 보는데 결제됐어"),
            ("왓챠", "url: https://watcha.example/account", 12900, "SUB-0002", "중복 결제된 것 같아"),
            ("멜론", "url: https://melon.example/my", 10900, "SUB-0003", "프로모션 끝나고 가격이 올랐어"),
            ("클라우드저장소", "url: https://cloudbox.example/billing", 11000, "SUB-0004", "용량 안 쓰는데 자동결제됐어"),
            ("뉴스프리미엄", "url: https://newspremium.example/my", 9900, "SUB-0005", "무료 체험 끝나고 바로 결제됐어"),
            ("피트니스앱플러스", "url: https://fitapp.example/account", 15000, "SUB-0006", "앱이 안드로이드에서 안 열려"),
            ("오디오북클럽", "url: https://audiobook.example/my", 14900, "SUB-0007", "가족 계정과 중복이야"),
            ("디자인툴프로", "url: https://designtool.example/billing", 29000, "SUB-0008", "회사 계정 생겨서 개인 건 해지"),
            ("게임패스", "url: https://gamepass.example/account", 16500, "SUB-0009", "아이 공부 때문에 해지하려고"),
            ("요리레시피박스", "url: https://recipebox.example/my", 13900, "SUB-0010", "구성이 광고와 달라"),
        ],
    },
    "app-refund": {
        "channel": "portal",
        "instruction": "아이가 실수 결제한 건데 인앱 결제 환불 신청해줘. 앱 환불 결과까지 확인 필요해.",
        "title": "{merchant} 인앱 결제 환불",
        "items": [
            ("구글플레이", "url: https://play.google.com/store/account", 99000, "GPA-3301-1", "아이가 게임 보석을 질렀어"),
            ("애플앱스토어", "url: https://reportaproblem.apple.com", 129000, "APL-7702", "유아 앱에서 연속 결제됐어"),
            ("구글플레이", "url: https://play.google.com/store/account", 33000, "GPA-3301-2", "구독인 줄 모르고 눌렀대"),
            ("애플앱스토어", "url: https://reportaproblem.apple.com", 45000, "APL-7703", "같은 아이템이 두 번 결제됨"),
            ("구글플레이", "url: https://play.google.com/store/account", 66000, "GPA-3301-3", "잠금 안 해둔 사이에 결제"),
            ("애플앱스토어", "url: https://reportaproblem.apple.com", 25000, "APL-7704", "체험판인 줄 알았는데 유료였어"),
            ("구글플레이", "url: https://play.google.com/store/account", 110000, "GPA-3301-4", "게임 패키지 중복 구매"),
            ("애플앱스토어", "url: https://reportaproblem.apple.com", 19000, "APL-7705", "앱이 실행도 안 돼"),
            ("구글플레이", "url: https://play.google.com/store/account", 54000, "GPA-3301-5", "환불 버튼이 안 보여"),
            ("애플앱스토어", "url: https://reportaproblem.apple.com", 88000, "APL-7706", "아이 계정 결제 제한 걸기 전 사고"),
        ],
    },
    "telecom-dispute": {
        "channel": "hybrid",
        "instruction": "요금이 이상해. 부당 청구 같으니 요금 이의신청 넣고 과오납 환불까지 받아줘.",
        "title": "{merchant} 요금 이의신청",
        "items": [
            ("SK텔레콤", "url: https://tworld.co.kr 상대 이메일: dispute@skt.example", 58000, "TEL-1001", "해지한 부가서비스가 계속 청구돼"),
            ("KT", "url: https://kt.com 상대 이메일: cs@kt.example", 72000, "TEL-1002", "로밍 요금이 이중 청구됐어"),
            ("LG유플러스", "url: https://lguplus.com 상대 이메일: help@lgu.example", 64000, "TEL-1003", "약정 할인 누락된 것 같아"),
            ("알뜰모바일", "url: https://mvno.example 상대 이메일: cs@mvno.example", 32000, "TEL-1004", "번호이동 후에도 요금이 나가"),
            ("SK브로드밴드", "url: https://skb.example 상대 이메일: net@skb.example", 41000, "TEL-1005", "해지한 인터넷 요금 청구"),
            ("KT인터넷", "url: https://kt.com 상대 이메일: inet@kt.example", 38500, "TEL-1006", "속도 저하 보상 약속 미이행"),
            ("헬로모바일", "url: https://hellomobile.example 상대 이메일: cs@hello.example", 29000, "TEL-1007", "데이터 추가 과금 이상"),
            ("SK텔레콤", "url: https://tworld.co.kr 상대 이메일: dispute@skt.example", 95000, "TEL-1008", "소액결제 차단했는데 결제됨"),
            ("LG유플러스", "url: https://lguplus.com 상대 이메일: help@lgu.example", 47000, "TEL-1009", "위약금 계산이 안 맞아"),
            ("KT", "url: https://kt.com 상대 이메일: cs@kt.example", 52000, "TEL-1010", "가족결합 할인 빠짐"),
        ],
    },
    "delivery-refund": {
        "channel": "portal",
        "instruction": "오배송이야. 반품 환불 접수하고 환불 완료까지 확인해줘.",
        "title": "{merchant} 오배송 환불",
        "items": [
            ("쿠팡", "url: https://coupang.com/orders", 42000, "CPG-5501", "다른 색상이 왔어"),
            ("마켓컬리", "url: https://kurly.example/orders", 38000, "KUR-5502", "신선식품이 상해서 왔어"),
            ("네이버쇼핑몰", "url: https://smartstore.example/orders", 56000, "NVR-5503", "주문 수량의 절반만 옴"),
            ("무신사", "url: https://musinsa.example/orders", 89000, "MSS-5504", "사이즈 교환 요청이 무시됐어"),
            ("오늘의집", "url: https://ohou.example/orders", 120000, "OHS-5505", "파손된 채 배송됨"),
            ("쿠팡", "url: https://coupang.com/orders", 27000, "CPG-5506", "배송 완료라는데 못 받았어"),
            ("11번가", "url: https://11st.example/orders", 33000, "EST-5507", "가품 의심 상품이 왔어"),
            ("지마켓", "url: https://gmarket.example/orders", 48000, "GMK-5508", "2주째 배송이 안 와"),
            ("티몬", "url: https://tmon.example/orders", 61000, "TMN-5509", "취소했는데 배송이 왔어"),
            ("위메프", "url: https://wemakeprice.example/orders", 39000, "WMP-5510", "구성품이 빠져 있어"),
        ],
    },
    "reservation-refund": {
        "channel": "email",
        "instruction": "예약 취소 환불 받아줘. 취소 수수료가 과해서 숙소 환불 기준대로 돌려받아야 해.",
        "title": "{merchant} 예약 취소 수수료",
        "items": [
            ("바다뷰펜션", "stay@badaview.example", 240000, "RSV-7701", "한 달 전 취소인데 50%를 떼겠대"),
            ("한옥스테이", "hanok@stay.example", 180000, "RSV-7702", "숙소 사정 취소인데 수수료 요구"),
            ("제주글램핑", "glamp@jeju.example", 320000, "RSV-7703", "태풍 경보로 못 갔어"),
            ("시티호텔", "resv@cityhotel.example", 150000, "RSV-7704", "더블부킹으로 방이 없었어"),
            ("스키리조트", "ski@resort.example", 280000, "RSV-7705", "리프트 운휴 보상을 거절당했어"),
            ("키즈풀빌라", "pool@kidsvilla.example", 350000, "RSV-7706", "수영장 고장인 걸 현장에서 알았어"),
            ("캠핑장온", "camp@on.example", 90000, "RSV-7707", "7일 전 취소 규정과 다르게 전액 몰수"),
            ("골프텔", "golf@tel.example", 410000, "RSV-7708", "우천 취소 보상 약속 미이행"),
            ("온천호텔", "spa@onsen.example", 220000, "RSV-7709", "시설 공사 중인 걸 숨겼어"),
            ("게스트하우스별", "star@guest.example", 70000, "RSV-7710", "노쇼 수수료가 잘못 청구됨"),
        ],
    },
    "warranty-claim": {
        "channel": "email",
        "instruction": "보증기간 안이야. 무상수리 아니면 교환 요구해줘. 하자 보상 끝까지 부탁해.",
        "title": "{merchant} 무상수리 청구",
        "items": [
            ("해피가전서비스", "as@happyhome.example", 0, "WRT-9901", "6개월 된 공기청정기 소음"),
            ("프리미엄오디오", "support@premaudio.example", 0, "WRT-9902", "헤드폰 단선, 보증 10개월 남음"),
            ("스마트워치코리아", "cs@smartwatch.example", 0, "WRT-9903", "배터리 부풀음"),
            ("키친메이트", "service@kitchenmate.example", 0, "WRT-9904", "전기포트 누수"),
            ("클린로봇", "as@cleanrobot.example", 0, "WRT-9905", "로봇청소기 센서 불량 재발"),
            ("홈카페머신", "cafe@homemachine.example", 0, "WRT-9906", "커피머신 히터 고장"),
            ("에어쿨텍", "cool@airtech.example", 0, "WRT-9907", "설치 하자로 누수 발생"),
            ("사운드바랩", "bar@soundlab.example", 0, "WRT-9908", "수리 2회에도 같은 고장"),
            ("게이밍기어", "gear@gaming.example", 0, "WRT-9909", "키보드 키 빠짐, 유상 전환 요구받음"),
            ("베이비모니터", "baby@monitor.example", 0, "WRT-9910", "카메라 화면 꺼짐 반복"),
        ],
    },
    "membership-cancel": {
        "channel": "portal",
        "instruction": "헬스장 환불 받아줘. 회원권 환불 해지 방어가 심한데 잔여분 꼭 돌려받아야 해.",
        "title": "{merchant} 회원권 해지 환불",
        "items": [
            ("파워짐", "url: https://powergym.example/my", 540000, "MEM-2201", "12개월 중 2개월 쓰고 이사"),
            ("요가스튜디오숨", "url: https://yogasoom.example/account", 390000, "MEM-2202", "강사 전원 교체로 그만두려고"),
            ("필라테스코어", "url: https://pilacore.example/my", 480000, "MEM-2203", "부상 진단서 있어"),
            ("수영클럽블루", "url: https://swimblue.example/account", 360000, "MEM-2204", "레인 축소로 이용이 어려워"),
            ("크로스핏박스", "url: https://cfbox.example/my", 420000, "MEM-2205", "지점 폐업 예정이래"),
            ("골프연습장그린", "url: https://golfgreen.example/account", 600000, "MEM-2206", "타석 예약이 항상 마감"),
            ("복싱클럽펀치", "url: https://boxpunch.example/my", 330000, "MEM-2207", "위약금 계산이 규정과 달라"),
            ("테니스아카데미", "url: https://tennisac.example/account", 450000, "MEM-2208", "코트 공사로 3개월 휴장"),
            ("클라이밍센터", "url: https://climbing.example/my", 280000, "MEM-2209", "야간 운영 중단으로 못 가"),
            ("댄스스튜디오온", "url: https://danceon.example/account", 310000, "MEM-2210", "환불 신청서를 안 받아줘"),
        ],
    },
    "deposit-recovery": {
        "channel": "hybrid",
        "instruction": "보증금 반환을 미루고 있어. 내용 정리해서 보증금 돌려받고 입금까지 확인해줘.",
        "title": "{merchant} 보증금 반환",
        "items": [
            ("스터디룸25", "url: https://study25.example 상대 이메일: room@study25.example", 100000, "DEP-4401", "정기권 보증금을 두 달째 안 줘"),
            ("공유오피스워크", "url: https://workshare.example 상대 이메일: cs@workshare.example", 300000, "DEP-4402", "퇴실 정산이 끝났는데 미반환"),
            ("정수기렌탈", "url: https://waterrental.example 상대 이메일: rental@water.example", 50000, "DEP-4403", "해지 후 설치 보증금 미반환"),
            ("파티룸모임", "url: https://partyroom.example 상대 이메일: host@party.example", 200000, "DEP-4404", "청소비 명목 과다 공제"),
            ("악기렌탈샵", "url: https://instrument.example 상대 이메일: rent@inst.example", 150000, "DEP-4405", "반납 완료했는데 연락 두절"),
            ("캠핑장비대여", "url: https://camprent.example 상대 이메일: gear@camp.example", 80000, "DEP-4406", "파손 안 했는데 공제하겠대"),
            ("정부24 미환급금", "url: https://gov.kr 상대 이메일: none", 0, "DEP-4407", "미수령 환급금 있는지 조회하고 수령까지"),
            ("보증금은행셰어", "url: https://bikeshare.example 상대 이메일: cs@bike.example", 30000, "DEP-4408", "탈퇴했는데 보증금 미입금"),
            ("키즈카페멤버십", "url: https://kidscafe.example 상대 이메일: cafe@kids.example", 60000, "DEP-4409", "폐업 공지 후 보증금 안내 없음"),
            ("코워킹락커", "url: https://locker.example 상대 이메일: locker@cowork.example", 40000, "DEP-4410", "락커 보증금 반환 지연"),
        ],
    },
}

_MAIL = """---
from: {frm}
to: {to}
subject: Fwd: {title}
---

{instruction}
업체: {merchant}
{contact_line}
{amount_line}주문번호: {order}

> From: {quoted_from}
> 제목: {title}
> {situation}. 관련 안내는 위 내용과 같습니다.
"""


def main() -> int:
    EMAILS.mkdir(parents=True, exist_ok=True)
    for old in EMAILS.glob("*.md"):
        old.unlink()
    index = []
    n = 0
    for ptype, spec in SCENARIOS.items():
        for merchant, contact, amount, order, situation in spec["items"]:
            n += 1
            title = spec["title"].format(merchant=merchant)
            if contact.startswith("url:"):
                contact_line = contact  # 포털형: url 그대로
                quoted_from = f"noreply@{common.slug(merchant, 12)}.example"
            elif "url:" in contact:
                contact_line = contact.replace(" 상대 이메일: none", "")  # 하이브리드
                quoted_from = (contact.split("상대 이메일:")[-1].strip()
                               if "상대 이메일:" in contact and "none" not in contact
                               else f"noreply@{common.slug(merchant, 12)}.example")
            else:
                contact_line = f"상대 이메일: {contact}"
                quoted_from = contact
            amount_line = f"금액: {amount}\n" if amount else ""
            fname = f"{n:03d}-{ptype}.md"
            (EMAILS / fname).write_text(_MAIL.format(
                frm=FROM, to=TO, title=title, instruction=spec["instruction"],
                merchant=merchant, contact_line=contact_line,
                amount_line=amount_line, order=order,
                quoted_from=quoted_from, situation=situation,
            ), encoding="utf-8")
            index.append({"n": n, "file": f"emails/{fname}", "type": ptype,
                          "channel": spec["channel"], "title": title,
                          "merchant": merchant, "amount": amount,
                          "situation": situation})
    (DEMO_DIR / "index.json").write_text(
        json.dumps({"version": "2026-11-03", "count": n, "emails": index},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"생성 완료: {n}통 → {EMAILS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
