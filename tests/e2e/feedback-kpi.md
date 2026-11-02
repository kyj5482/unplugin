# E2E 테스트케이스 — 피드백·KPI (FBK)

## TC-FBK-001: 피드백 표준 태깅 강제
- 상태: FAIL
- 우선순위: P0
- 유스케이스: UC-D1
- 워크플로우: workflows/customer-request.md

**Given** 위임 1건이 완료되었다
**When** CS가 피드백을 수집하면
**Then** `departments/cs/feedback/`의 파일에 필수 frontmatter 5개(delegation, satisfaction, offline_realized, offline_story, reclaimed_hours)가 모두 채워진다 (모르면 "미확인"으로라도 명시)
- 검증: 피드백 파일 frontmatter 필드 존재를 스크립트로 검사 (추후 자동화 1순위)

## TC-FBK-002: offline_realized=no → 원인 분류·핸드오프
- 상태: FAIL
- 우선순위: P0
- 유스케이스: UC-D2

**Given** 피드백에 offline_realized=no 가 기록되었다 ("시간은 생겼는데 그냥 유튜브 봤어요")
**When** CS가 피드백을 처리하면
**Then** ① 원인이 분류되고(추천 부적합 / 동기 부족 / 시간 파편화 등) ② 상품기획으로 개선 핸드오프가 Flow에 기록된다 — 이 케이스가 우리 KPI의 최대 적이다
- 검증: no 케이스 리허설, 원인 태그와 핸드오프 기록 확인

## TC-FBK-003: Reclaimed Hours 깔때기 집계
- 상태: FAIL
- 우선순위: P0
- 유스케이스: UC-D3

**Given** flows/에 완료된 위임 3건, feedback/에 피드백 3건이 있다
**When** KPI 집계를 실행하면 (초기: 에이전트 수동 집계 → 목표: 스크립트)
**Then** Delegated Hours 합계, Reclaimed Hours 합계, 전환율이 산출되고 `ops/` 아래 주간 리포트로 저장된다
- 검증: 샘플 데이터 3건으로 집계 리허설, 수기 계산과 일치 확인

## TC-FBK-004: 반복 불만 → 개선 과제 전환
- 상태: FAIL
- 우선순위: P1
- 유스케이스: UC-D4

**Given** 서로 다른 고객 2명 이상에게서 같은 유형의 불만(예: 승인 요청이 너무 잦음)이 접수되었다
**When** CS가 주간 피드백을 정리하면
**Then** 반복 불만이 감지되어 담당 부문(이 예시는 IT)으로 개선 과제 Flow가 생성된다
- 검증: 동일 유형 불만 2건 투입 후 개선 Flow 생성 확인
