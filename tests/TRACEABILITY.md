# 추적성 매트릭스 — UC ↔ TC ↔ 구현

유스케이스가 테스트케이스로, 테스트케이스가 구현으로 이어지는지 추적한다.
상태의 단일 출처는 각 TC 문서의 `- 상태:` 필드이며, 집계는 `python3 tests/status.py`.

| UC | 유스케이스 요약 | TC | 우선순위 | 구현 담당 | 구현 대상 (만들어야 PASS) |
|---|---|---|---|---|---|
| UC-A1 | 문진 → 첫 위임 1개 | TC-ONB-001 | P0 | cs | 문진 진행 절차 + 프로필 저장 형식 |
| UC-A2 | 문진 이어하기 | TC-ONB-002 | P1 | cs, it | 프로필의 부분 응답 저장·재개 |
| UC-A3 | 위임 금지 목록 | TC-ONB-003 | P0 | cs, product | 프로필 금지 목록 필드 + 추천 시 필터 |
| UC-A4 | 일괄 위임 축소 | TC-ONB-004 | P0 | cs | 대기 후보 기록 절차 |
| UC-A5 | 문진 기반 추천 근거 | TC-ONB-005 | P0 | product | 추천 문서 양식(근거 필수) |
| UC-A6 | 온보딩 미완료 시 위임 | TC-ONB-006 | P1 | cs | 최소 필수 항목 정의 |
| UC-A7 | 같은 타입 전환 사례 | TC-ONB-007 | P0 | product, it | docs/test.html 타입 결과 + 실측 교체 |
| UC-B1 | 장보기 위임 성공 | TC-DEL-001 | P0 | it | 브라우저 세션 실행 + Flow 기록 |
| UC-B2 | 선택지 → 고객 확인 | TC-DEL-002 | P0 | it, cs | 확인 요청 묶음 규칙 |
| UC-B3 | 탐색은 요약 반환 | TC-DEL-003 | P0 | it | 반환 양식 (추천1+대안2) |
| UC-B4 | 수행 불가 처리 | TC-DEL-004 | P0 | it | 재시도·중단·에스컬레이션 규칙 |
| UC-B5 | 결제 승인 게이트 | TC-DEL-005 | P0 | it | 승인 한도 설정 + 결제 전 정지 |
| UC-B6 | 보안 원칙 | TC-DEL-006 | P0 | it | 자격증명 취급 규칙 + 기록 금지 검사 |
| UC-B7 | 범위 밖 거절 | TC-DEL-007 | P0 | concierge | 거절 기준 + 대안 안내 |
| UC-B8 | 상태 조회 | TC-DEL-008 | P1 | cs | Flow 기반 상태 응답 |
| UC-B9 | 진행 중 취소 | TC-DEL-009 | P1 | it | 안전 중단 + 중간 결과 반환 |
| UC-B10 | 완료 증빙·검증 | TC-DEL-010 | P0 | it, concierge | 증빙 첨부 규칙 + 완결 게이트 |
| UC-B11 | 프롬프트 인젝션 방어 | TC-DEL-011 | P0 | it | 인젝션 테스트 페이지 + 방어 규칙 |
| UC-B12 | Takeover 핸드오버 | TC-DEL-012 | P1 | it | Takeover 모드 절차 |
| UC-B13 | 반복 위임 자동 실행 | TC-DEL-013 | P1 | it | 반복 스케줄 + 회차 기록 |
| UC-C1 | 시간 추정 + 추천 | TC-OFF-001 | P0 | product | 경험 카탈로그 + 추천 로직 v0 |
| UC-C2 | 거절 → 재추천 | TC-OFF-002 | P0 | product, cs | 거절 사유 → 프로필 제약 누적 |
| UC-C3 | 추천 → 예약 대행 | TC-OFF-003 | P1 | concierge | 추천-위임 연결 Flow |
| UC-C4 | 재문진 실측 | TC-OFF-004 | P0 | cs | 재문진 절차 + 실측 필드 |
| UC-D1 | 피드백 태깅 | TC-FBK-001 | P0 | cs, it | frontmatter 검사 스크립트 (자동화 1순위) |
| UC-D2 | 미전환 원인 분류 | TC-FBK-002 | P0 | cs | 원인 분류 체계 + 핸드오프 |
| UC-D3 | KPI 깔때기 집계 | TC-FBK-003 | P0 | it | 집계 스크립트 + 주간 리포트 양식 |
| UC-D4 | 반복 불만 → 과제 | TC-FBK-004 | P1 | cs | 주간 피드백 정리 절차 |
| UC-E1 | 스토리 → 승인 → 게시 | TC-MKT-001 | P1 | marketing | drafts/published 이동 규칙 |
| UC-E2 | 가상 스토리 거부 | TC-MKT-002 | P0 | marketing | (에이전트 규칙 — 리허설로 검증) |
| UC-E3 | 익명화 | TC-MKT-003 | P0 | marketing | 익명화 체크리스트 |
| UC-F1 | 대표 지시 처리 | TC-OPS-001 | P0 | concierge | (워크플로우 — 리허설로 검증) |
| UC-F2 | Unified Flow 완전성 | TC-OPS-002 | P0 | concierge | Flow 템플릿 준수 검사 |
| UC-F3 | 슬롯 초과 큐 대기 | TC-OPS-003 | P1 | it | 파일 기반 큐 v0 |
| UC-F4 | 큐 순서·티어 슬롯 | TC-OPS-004 | P1 | it | 큐 처리 규칙 |
| UC-F5 | 해지·환불 | TC-OPS-005 | P2 | product, cs | 환불 규정(ops/pricing.md 추가) |
| UC-F6 | 한도 사전 통지 | TC-OPS-006 | P2 | it, cs | 사용량 추적 |
| UC-F7 | 장기 대기 타임아웃 | TC-OPS-007 | P1 | it, cs | 큐 타임아웃·통지 규칙 |
| UC-G1 | 전용 주소 발급·격리 | TC-EML-001 | P0 | it | 주소↔고객 매핑 + 격리 |
| UC-G2 | 포워딩 위임 접수 | TC-EML-002 | P0 | it, concierge | 메일 파이프라인 v0 (inbox/ 시뮬레이션) |
| UC-G3 | 시스템 발신 자동 처리 | TC-EML-003 | P1 | it | 발신자 등록 + 배치 요약 |
| UC-G4 | 이메일 규칙 실행 | TC-EML-004 | P0 | it, product | 규칙 포맷 + 조건 판정 |
| UC-G5 | 발신자 검증·인젝션 방어 | TC-EML-005 | P0 | it | 검토함 격리 + 신뢰 등급 |

## 커버리지 현황

- 유스케이스 43개 전부 TC로 커버됨 (1:1), 벤치마킹 근거: `ops/benchmarking.md`
- P0 28건 = 베타(대표 자가 사용 + 지인 1~2명) 전에 PASS 해야 하는 범위
- P1 13건 = 유료 고객 받기 전 / P2 2건 = 과금 운영 본격화 전 (합계 43 = `python3 tests/status.py`와 일치해야 함)
- 보류 2건(멀티채널 dedupe, 결제수단 사전 등록)은 benchmarking.md "체크리스트 반영 현황" 참고
