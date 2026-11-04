# E2E 테스트케이스 — 시간 배당·팁 엔진 (DIV / TIP, 피벗 2026-11-04)

피벗 기본 모드 검증: 우리는 일을 대신하지 않는다 — 팁 카드 회신 + 완료 보고
자동 적립. 보고 규약은 "사용자가 Muze 등 에이전트에 '끝나면 전용주소로 제목
[보고] 메일' 한 줄을 붙인다" (대표 확정, flows/2026-11-04-pivot-time-dividend.md).
셀프테스트: core/selftest_dividend.py (12/12 PASS). 실 Muze 발신 메일로는
대표 맥북에서 재검증 필요.

## TC-DIV-001: [보고] 마커 보고 → 자동 적립 (유형 매칭)
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — grocery-recurring 매칭, baseline_minutes 적립, 적립 확인 메일 1통(누적 잔고 포함), 수동 입력 경로 없음
- 우선순위: P0

**Given** 고객이 팁 카드대로 Muze에 일을 시켰고, 완료 보고 메일(제목 [보고])이 전용 주소로 수신됐다
**When** mail-poll 이 메일을 처리하면
**Then** ① 위임 접수가 아니라 적립으로 분기되고 ② classify 유형 매칭으로 플러그인의 baseline_minutes·emotion_load 가 적립되며 ③ 고객에게 "업무 · +N분 · 감정 ●●○○○ / 누적 잔고" 적립 확인 메일이 발송된다 — 고객은 아무것도 기록하지 않았다
- 검증: ledger.json 이벤트·totals, outbox 적립 메일, 큐 미생성

## TC-DIV-002: 마커 없는 보고 — 완료 키워드 관대 판정
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — "끝냈습니다/완료" 본문 휴리스틱 적립
- 우선순위: P0

**Given** 에이전트가 [보고] 마커 없이 완료 메일을 보냈다 (Muze가 지시를 축약한 경우)
**When** 본문에 완료 키워드(완료/처리했/끝냈/done 등)가 있으면
**Then** 보고로 관대하게 판정해 적립한다 — 단, 진행 중 스레드 회신(thread 지정)은 보고로 보지 않는다
- 검증: thread 없는 완료 키워드 메일 → report_accrued

## TC-DIV-003: 스트레스 유형 보고 — 감정 가중
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — 환불 분쟁 보고 emotion_load ≥ 4, saved ≥ 90분
- 우선순위: P0

**Given** 환불·분쟁 등 스트레스 유형(core/stress.py)의 완료 보고가 수신됐다
**When** 적립을 계산하면
**Then** 감정 부하가 가중된다(≥4) — 이런 일은 시간보다 아낀 감정이 크다
- 검증: ledger 이벤트의 emotion_load·saved_minutes

## TC-DIV-004: 임계치 도달 → 넥스트 무브먼트 제안 (중복 금지)
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — 120분 임계치 1회 제안, 같은 구간 추가 적립에 중복 없음, 다음 구간 진입 시 재발송
- 우선순위: P0

**Given** 잔고가 profile.movement_threshold_minutes(기본 180분)를 넘었다
**When** 적립이 그 구간을 처음 넘기면
**Then** 관계·배움·오감 3축 무브먼트 제안 메일 1통이 발송되고, 같은 구간에서는 다시 보내지 않으며, 다음 구간 진입 시에만 재발송된다
- 검증: outbox 무브먼트 메일 수, ledger.last_suggested_at_minutes

## TC-DIV-005: 미매칭 보고 — 기본값 적립
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — 30분/감정 2, matched:false 기록
- 우선순위: P1

**Given** 카탈로그 어느 유형에도 매칭되지 않는 보고가 수신됐다
**When** 적립하면
**Then** 기본값(30분/감정 2)으로 적립하되 matched:false 로 기록한다 — 미매칭 누적은 카탈로그 보강(상품기획·IT) 신호다
- 검증: ledger 이벤트 matched/saved_minutes/emotion_load

## TC-DIV-006: 잔고 일관성 — totals = 이벤트 합
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — 6건 적립 후 totals == Σevents
- 우선순위: P1

**Given** 여러 건의 보고가 적립됐다
**When** ledger totals 를 확인하면
**Then** totals.saved_minutes 는 이벤트 합과 항상 일치한다 (Yohana 교훈 — "절약한 시간" 집계 정확성이 상품이다)
- 검증: ledger.json totals vs events 합

## TC-TIP-001: 포워딩 업무 → 팁 카드 회신 (대행 접수 없음)
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — tip_sent, 큐 0건, [보고] 한 줄 + 전용주소 포함
- 우선순위: P0

**Given** 고객이 업무 메일을 전용 주소로 포워딩했다 (피벗 기본 모드)
**When** mail-poll 이 처리하면
**Then** ① 대행 큐에 넣지 않고 ② "에이전트에 이렇게 시키세요" 팁 카드(프롬프트 템플릿 + 예상 절약 분 + 감정 부하)를 회신하며 ③ 프롬프트에 [보고] 한 줄(고객 전용주소)이 항상 포함된다 — 팁→실행→보고→적립 루프의 입구
- 검증: outbox 팁 메일, 큐 상태, Flow 완료 처리

## TC-TIP-002: 스트레스 유형 → 고급 팁 ("입금 확인까지 시키는 법")
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — 입금 확인·재촉 2회·에스컬레이션 지시 포함, 케이스 미생성
- 우선순위: P0

**Given** 환불·분쟁 등 스트레스 유형 업무가 포워딩됐다
**When** 팁 카드를 만들면
**Then** 플레이북(core/stress.py)의 요지 — 접수가 아니라 입금 확인까지, 무응답 시 재촉 2회, 그래도 안 되면 에스컬레이션 — 가 프롬프트에 반영된 고급 팁이 나간다 (케이스·협상 엔진은 동결, 직접 수행하지 않음)
- 검증: 팁 메일 본문, cases 미생성

## TC-TIP-003: 미매칭 업무 → 범용 팁
- 상태: PASS
- 검증 기록: core/selftest_dividend.py (2026-11-04) — matched:false 범용 프롬프트 + 보고 한 줄 + 플레이스홀더 주소
- 우선순위: P1

**Given** 카탈로그 밖 업무 텍스트로 팁을 요청했다 (CLI `tips` 포함)
**When** 매칭이 없으면
**Then** 범용 프롬프트 골격에 [보고] 한 줄을 붙인 팁이 나간다 — 고객 미지정 시 주소는 `<내 전용주소>` 플레이스홀더
- 검증: tips.make_tip 반환값
