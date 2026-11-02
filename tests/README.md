# tests/ — E2E 테스트 전략

Unplugin은 **테스트케이스 주도(TDD)** 로 개발한다. 고객 시나리오의 모든 유스케이스를 먼저 테스트케이스로 정의하고, 테스트가 PASS 되도록 개발을 진행한다.

## 구조

```
tests/
├── USE-CASES.md        # 고객 시나리오 유스케이스 인벤토리 (UC-*)
├── TRACEABILITY.md     # UC ↔ TC ↔ 워크플로우 ↔ 상태 매트릭스
├── status.py           # TC 상태 집계 (python3 tests/status.py)
└── e2e/                # 도메인별 테스트케이스 (TC-*)
    ├── onboarding.md   # 유입·문진·첫 위임 선정
    ├── delegation.md   # 위임 실행 (AI 브라우저 세션)
    ├── offline.md      # 오프라인 전환·추천
    ├── feedback-kpi.md # 피드백·KPI 집계
    ├── marketing.md    # 콘텐츠 파이프라인
    └── operations.md   # 대표 운영·큐·과금
```

## 테스트케이스 형식

각 TC는 Given/When/Then + 검증 방법을 갖는다:

```markdown
## TC-<도메인>-<번호>: <제목>
- 상태: PASS | FAIL | BLOCKED
- 우선순위: P0(베타 필수) | P1(정식 출시) | P2(확장)
- 유스케이스: UC-*
- 워크플로우: workflows/*.md

**Given** ... **When** ... **Then** ...
- 검증: <맥북에서 확인하는 구체적 방법>
```

## 실행 단계 (현 수준 → 자동화)

1. **지금 (수동 리허설)**: 대표가 Claude Code에서 "고객 요청: ..." 시나리오를 입력하고, TC의 Then 조건과 산출물(flows/, feedback/ 파일)을 눈으로 대조 → `상태:` 갱신
2. **다음 (반자동)**: IT 부문이 TC별 검증 스크립트 작성 — 산출 파일의 존재·필수 필드·태깅을 기계 검증
3. **목표 (자동)**: 큐/문진/추천이 코드화되면 TC를 실제 테스트 코드로 전환, `status.py`가 CI 역할

## 규칙

- **새 기능은 TC부터**: 어떤 부문이든 기능을 추가하려면 해당 도메인 파일에 TC를 먼저 추가한다.
- **상태는 정직하게**: 검증을 통과한 것만 PASS. 돌려보지 않은 것은 FAIL로 둔다.
- **집계**: `python3 tests/status.py` 로 전체 PASS/FAIL 현황과 P0 잔여를 확인한다.
