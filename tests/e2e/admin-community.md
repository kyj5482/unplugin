# E2E 테스트케이스 — Admin·측정 보정 (ADM) / 커뮤니티 (CMU)

피벗(2026-11-04, ops/pivot-2026-11-04.md) 신규 영역. 검증: core/selftest_admin.py,
core/selftest_community.py + 피벗 데모 여정(`python3 -m core demo-run 1~5`).

## TC-ADM-001: 적립 산정 근거(basis) 기록
- 상태: PASS
- 검증 기록: core/selftest_admin.py (2026-11-04) — baseline·factor·evidence 기록, 기본 보정 1.0
- 우선순위: P0

**Given** 고객의 trusted_senders에 등록된 에이전트가 [보고] 메일을 보냈다
**When** 자동 적립이 일어나면
**Then** 적립 이벤트에 basis={기준치 분, 개인 보정 계수, 출처(evidence)}가 기록된다
- 검증: ledger.json의 basis 필드, evidence는 ops/research-time-baselines.md#<카테고리>

## TC-ADM-002: 개인 보정(time_factor) — 사람마다 다른 소요 시간
- 상태: PASS
- 검증 기록: core/selftest_admin.py (2026-11-04) — ×1.5 적용, 0.5~2.0 클램프
- 우선순위: P0

**Given** Admin이 `calibrate <고객> <계수>`로 보정을 조정했다
**When** 다음 보고가 적립되면
**Then** 절약 분 = 기준치 × 계수(0.5~2.0 클램프)로 계산된다 — 고객에게 수동 기록을 요구하지 않는다

## TC-ADM-003: 적립 확인 메일의 산정 근거 명시
- 상태: PASS
- 검증 기록: core/selftest_admin.py (2026-11-04)
- 우선순위: P0

**Given** 적립이 발생했다
**When** 적립 확인 메일이 발송되면
**Then** "산정 근거: 업무 유형 기준치 N분 × 개인 보정 ×F — 출처 <문서>" 한 줄이 포함된다
(신빙성 — 수치의 출처가 고객에게도 보인다)

## TC-ADM-004: Admin 운영판 생성
- 상태: PASS
- 검증 기록: core/selftest_admin.py (2026-11-04) + demo-run 여정 7단계
- 우선순위: P0

**Given** 적립·팁·커뮤니티 데이터가 있다
**When** `python3 -m core admin`을 실행하면
**Then** data/admin.html에 ①고객별 잔고(보정 포함) ②보고 피드(에이전트별) ③무브먼트 현황
④팁 발송 ⑤커뮤니티 그룹 ⑥미매칭 백로그가 생성된다 (로컬 전용·비공개)

## TC-CMU-001: 공통 위임 특성 그룹 자동 편성
- 상태: PASS
- 검증 기록: core/selftest_community.py (2026-11-04)
- 우선순위: P0

**Given** 여러 고객이 같은 카테고리 업무를 적립했다
**When** 커뮤니티 편성이 돌면
**Then** 고객별 상위 위임 유형 기준으로 같은 유형 그룹(예: 장보기 해방 클럽)에 자동 편성된다
— 가입 절차 없음(당근의 '거래'처럼, '위임'이라는 행동이 곧 멤버십)

## TC-CMU-002: 무브먼트 제안의 동네 모임 섹션
- 상태: PASS
- 검증 기록: core/selftest_community.py (2026-11-04) — 같은 그룹·같은 region 2인 이상일 때만, 익명
- 우선순위: P0

**Given** 임계치 도달 고객의 그룹에 같은 지역(region) 멤버가 더 있다
**When** 무브먼트 제안 메일이 나가면
**Then** "같은 그룹 모임 제안" 섹션이 붙는다 — 이웃의 실명·주소는 노출되지 않는다

## TC-CMU-003: 그룹 다이제스트 — 익명·주기 제한
- 상태: PASS
- 검증 기록: core/selftest_community.py (2026-11-04)
- 우선순위: P1

**Given** 2인 이상 그룹이 있다
**When** community-run이 돌면
**Then** 멤버 전원에게 다이제스트(규모·합산 절약·익명 팁) 1통씩, 닉네임만 노출,
같은 그룹에는 7일 내 재발송하지 않는다 (--force 예외)

## TC-CMU-004: 지역 미등록 고객 보호
- 상태: PASS
- 검증 기록: core/selftest_community.py (2026-11-04)
- 우선순위: P1

**Given** region이 없는 고객이 임계치에 도달했다
**When** 무브먼트 제안이 나가면
**Then** 모임 섹션은 붙지 않는다 (지역 공개는 고객 선택)
