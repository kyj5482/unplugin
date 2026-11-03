# demo/ — 스트레스 업무 데모 (100통)

미루면 스트레스가 쌓이는 장기·감정소모형 업무(환불·분쟁·해지·보증금) 100건을
실제 처리 흐름 그대로 시연하는 데모다. "요청 접수"가 아니라 **"돈이 실제로
들어왔는지"까지** 추적하는 것이 핵심이다.

## 구성

```
demo/
├── emails/            # 샘플 메일 100통 (10유형 × 10통, core 메일 포맷)
├── index.json         # 매니페스트 (번호·유형·채널·금액·상황)
├── generate_emails.py # 결정적 생성기 — 수정 후 재실행하면 100통 재생성
├── runtime/           # demo-run 격리 실행 환경 (git 제외 — 실데이터 무오염)
└── CLAUDE.md          # 클로드 CLI로 시연하는 방법
```

## 10개 유형 (core/stress.py 플레이북과 1:1)

| 유형 | 채널 | 번호 | 예시 |
|---|---|---|---|
| refund-dispute 구매·클래스 환불 분쟁 | email 협상 | 1~10 | 공방 환불 거부 → 멀티라운드 요구 |
| edu-refund 학원·인강 환불 | email 협상 | 11~20 | 중도 해지 위약금 분쟁 |
| subscription-refund 구독 해지·환불 | portal | 21~30 | OTT 미사용분 일할 환불 |
| app-refund 인앱 결제 환불 | portal(봇차단) | 31~40 | 구글/애플 — 사람 개입 가이드 |
| telecom-dispute 요금 이의신청 | hybrid | 41~50 | 과오납 환급 + 메일 추적 |
| delivery-refund 오배송 환불 | portal | 51~60 | 쇼핑몰 반품·환불 접수 |
| reservation-refund 예약 취소 수수료 | email 협상 | 61~70 | 숙소 위약금 분쟁 |
| warranty-claim 무상수리·교환 | email 협상 | 71~80 | 보증기간 내 하자 보상 |
| membership-cancel 회원권 해지 환불 | portal | 81~90 | 헬스장 해지 방어 돌파 |
| deposit-recovery 보증금·환급금 회수 | hybrid | 91~100 | 미반환 보증금, 정부24(Takeover) |

## 실행

```bash
python3 -m core demo-list          # 100건 목록
python3 -m core demo-run 1         # 이메일 협상형 (거부→재요구→수락→입금 확인)
python3 -m core demo-run 21        # 포털형 (egolite 수행→증빙→포털 재확인)
python3 -m core demo-run 31        # 봇차단형 (HITL 가이드→완료 보고→고객 확인)
python3 -m core demo-run 1 --fresh # runtime 초기화 후 실행
```

각 실행은 `demo/runtime/`(격리)에 flow·케이스·증빙·고객 상태 메일을 남기므로,
끝난 뒤 파일을 직접 열어 전 과정을 재구성할 수 있다.
