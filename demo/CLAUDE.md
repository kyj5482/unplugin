# demo/ 작업 규칙 — 클로드 CLI 시연 가이드 (피벗 2026-11-04)

이 디렉토리는 **피벗 데모(시간 배당 여정 5건, 메일 85통)**의 소유지다.
대행 시대의 스트레스 100통은 `demo/legacy/`에 동결 보존(`--legacy`로 재생).

## Step-by-Step 시연 절차 (피벗 여정)

1. **선택**: `python3 -m core demo-list` — 고객 5명(지역·개인 보정 다양)의 여정 중 선택.
2. **실행**: `python3 -m core demo-run <1~5> --fresh` — 격리 환경에서 단계별 출력:
   이웃 적립(배경) → 포워딩→팁 카드 회신 → 보고 수신→자동 적립(산정 근거 표시)
   → 잔고 → 임계치→무브먼트 제안(+동네 모임 섹션) → 커뮤니티 다이제스트 → Admin 생성.
   출력을 요약하지 말고 단계 흐름을 그대로 보여준다.
3. **검증**: 실행 후 아래를 열어 확인시킨다.
   - 적립 원장: `demo/runtime/data/dividend/<고객>/ledger.json` (events[].basis — 기준치×보정×출처)
   - 고객 메일: `demo/runtime/data/outbox/*.md` (팁 카드 / 적립 확인 / 무브먼트+모임 / 다이제스트)
   - Admin 운영판: `demo/runtime/data/admin.html` (브라우저로 열기)
4. **수동 분기 시연** (대표가 원하면): `UNPLUGIN_DATA=demo/runtime/data
   UNPLUGIN_FLOWS=demo/runtime/flows` 환경에서(레거시 변수 없이)
   `demo/customers/<cid>` 프로필을 data/customers/에 복사 →
   `demo/emails/NNN-*.md`를 inbox에 투입 → `mail-poll → dividend →
   calibrate <cid> <계수> → mail-poll(보정 반영 확인) → community-run --force → admin`
   을 한 명령씩 실행하며 틱마다의 변화를 보여준다.

## 레거시 시연 (동결 대행 경로)

`python3 -m core demo-run <1~100> --legacy --fresh` — 접수→협상/포털→입금 확인.
무결성은 core/selftest_stress.py STR-008이 검증(demo/legacy/ 기준).

## 규칙

- `demo/emails/`·`demo/customers/`는 손으로 고치지 않는다 —
  `demo/generate_emails.py`를 수정하고 재생성한다 (결정적, 85통).
- `demo/legacy/`는 동결 — 수정 금지.
- `demo/runtime/`은 격리 실행장이다. 실데이터(`data/`)·`flows/`를 오염시키지 않는다.
- 보고 발신 주소는 고객 trusted_senders의 에이전트 주소여야 적립된다 —
  미등록 발신 시연은 "격리됨"이 정상 동작이다.
