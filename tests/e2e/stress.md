# E2E 테스트케이스 — 스트레스 업무 케이스 (STR)

미루면 스트레스가 쌓이는 장기·감정소모형 업무(환불·분쟁·해지·보증금)를
케이스로 우선 처리하고, "요청 접수"가 아니라 "결과 확인(입금)"까지 추적한다.
구현: core/stress.py, cases.py, negotiation.py, egolite.py, hitl.py, tracking.py, agents.py

## TC-STR-001: 스트레스 유형 분류·우선 처리
- 상태: PASS
- 검증 기록: core/selftest_stress.py + tests/e2e_runner.py (2026-11-03) — 10개 플레이북 전수 분류, 나중에 접수된 스트레스 건이 일반 건보다 먼저 착수
- 우선순위: P0
- 유스케이스: UC-S1

**Given** 고객이 환불·분쟁·해지류 메일을 포워딩했다
**When** 컨시어지가 접수하면
**Then** ① 10개 스트레스 플레이북 중 올바른 유형으로 분류되고 ② 케이스가 생성되며 ③ 큐에서 일반 위임보다 먼저(priority=high) 착수된다 — 멘탈 케어를 위해 미루던 일 먼저
- 검증: 일반 위임 선접수 후 스트레스 건 투입, 착수 순서 확인

## TC-STR-002: 인텐트 추출 → 케이스 생성
- 상태: PASS
- 검증 기록: core/selftest_stress.py + tests/e2e_runner.py (2026-11-03)
- 우선순위: P0
- 유스케이스: UC-S2

**Given** 포워딩 메일에 업체·상대 이메일·금액·주문번호·포털 URL이 섞여 있다
**When** 케이스가 생성되면
**Then** 인텐트(goal·merchant·merchant_email·amount·order_no·portal_url)가 구조화되어 저장되고, 채널(email/portal/hybrid)에 맞는 역할의 에이전트 직원이 배정된다
- 검증: 샘플 메일 투입 후 케이스 JSON 인텐트 필드 전수 확인

## TC-STR-003: 이메일 협상 멀티라운드
- 상태: PASS
- 검증 기록: core/selftest_stress.py (거부 사다리·부분 제안 2분기·에스컬레이션) + e2e_runner (수락→추적) (2026-11-03)
- 우선순위: P0
- 유스케이스: UC-S3

**Given** 이메일 채널 케이스가 착수되었다
**When** 상대방과 회신을 주고받으면
**Then** ① 1차 정중한 요구 → 거부 시 근거 재제시 → 최후 통첩의 라운드 사다리로 진행되고(히스토리 포함) ② 부분 제안은 요구액 90% 미만이면 임의 수락 없이 고객에게 1회 질문 ③ 최대 라운드 초과 시 임의 진행 없이 에스컬레이션(소비자원 등)을 제안하며 ④ 모든 라운드가 케이스·Flow에 기록된다
- 검증: 거부 반복/부분 제안/수락 시나리오 리허설

## TC-STR-004: 포털(egolite) 실행 + 증빙
- 상태: PASS
- 검증 기록: core/selftest_stress.py + selftest_delegation.py (2026-11-03) — 시뮬레이션. egolite 원격 세션(UNPLUGIN_EGOLITE_URL)·맥북 실브라우저 실증 시 재검증
- 우선순위: P0
- 유스케이스: UC-S4

**Given** 포털 채널 케이스(구독 해지, 쇼핑몰 환불 등)가 착수되었다
**When** egolite 어댑터가 해당 시스템에 접속해 절차를 수행하면
**Then** ① 인텐트 기반으로 환불/해지 절차가 완료되고 ② 접수번호·단계 로그가 증빙 파일로 남으며 ③ 페이지 내 인젝션 지시는 데이터로만 취급·감지 시 중단된다
- 검증: 포털 레지스트리(core/portals.json) 기반 리허설 + 인젝션 포털 투입

## TC-STR-005: 봇 차단 → 사람 개입(HITL) → 재개
- 상태: PASS
- 검증 기록: core/selftest_stress.py + selftest_delegation.py (2026-11-03)
- 우선순위: P0
- 유스케이스: UC-S5

**Given** 대상 포털이 AI/로봇 접근을 차단한다 (구글플레이·애플·정부24 등)
**When** 차단이 감지되면
**Then** ① 자동 우회를 시도하지 않고 ② 직원이 그대로 따라 할 클릭 단위 가이드(data/handoff/*.md)가 발행되며 ③ `hitl-done` 완료 보고(접수번호) 즉시 케이스가 자동 재개되어 추적으로 넘어간다. 본인 인증 구간은 Takeover(기록 중지)로 명시된다
- 검증: 차단 포털 데모(demo-run 31) 리허설, 가이드·재개 확인

## TC-STR-006: 완료 추적 — 입금 확인까지
- 상태: PASS
- 검증 기록: core/selftest_stress.py (넛지 2회→에스컬레이션) + e2e_runner (입금 확인 후 완결) (2026-11-03)
- 우선순위: P0
- 유스케이스: UC-S6

**Given** 환불이 접수/합의되었다
**When** 추적 틱이 돌면
**Then** ① 입금(처리 완료) 확인 전에는 Flow가 절대 완료되지 않고 ② 기한 초과 시 상대방에게 확인 요청을 최대 2회 보내며 ③ 그래도 안 되면 고객에게 에스컬레이션 선택지를 제안하고 ④ 확인(상대 통보/포털 재확인/고객 회신) 후에만 증빙과 함께 완결된다
- 검증: 기한 조작 리허설로 넛지·에스컬레이션·확정 3분기 확인

## TC-STR-007: AI 에이전트 직원 조직
- 상태: PASS
- 검증 기록: core/selftest_stress.py (2026-11-03)
- 우선순위: P1
- 유스케이스: UC-S7

**Given** 회사는 대표 1인 + AI 에이전트 직원들(core/agents_roster.json)로 운영된다
**When** 케이스·위임이 접수되면
**Then** ① 역할(concierge/resolver/negotiator/tracker/coordinator)에 맞는 직원 중 부하가 가장 적은 직원이 배정되고 ② Flow 단계에 "부문/직원" 형식으로 누가 했는지 기록되며 ③ `python3 -m core agents`로 직원별 부하를 볼 수 있다
- 검증: 로스터 5역할 존재 + 배정·표기 확인

## TC-STR-008: 데모 100통 + 단계별 실행
- 상태: PASS
- 검증 기록: core/selftest_stress.py (100통 무결성·분류 전수) + demo-run 1/21/31 수동 리허설 (2026-11-03)
- 우선순위: P0
- 유스케이스: UC-S8

**Given** demo/emails에 10개 유형 × 10통 = 100통의 샘플 메일이 있다
**When** `python3 -m core demo-run <n>`을 실행하면
**Then** ① 선택한 1통이 격리 환경(demo/runtime)에서 접수→분류→협상/포털→(HITL)→추적→입금 확인→완결까지 단계별 번호와 함께 처리되고 ② 100통 전부 포맷·수신 주소·플레이북 분류가 정합하며 ③ 클로드 CLI가 각 단계를 눈으로 확인할 수 있다
- 검증: `python3 -m core demo-list` 100건 + 채널별 대표 시나리오(1·21·31) 실행
