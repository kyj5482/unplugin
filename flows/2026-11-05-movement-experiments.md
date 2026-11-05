# Flow: 무브먼트 실험 10종 — 오프라인 전환 핵심 메커니즘

- **ID**: 2026-11-05-movement-experiments
- **유형**: 대표 지시
- **접수**: 2026-11-05
- **상태**: 완료 — 대표 평가 대기 (office "무브먼트 실험" 탭에서 Go/보류/No-go 입력)
- **관련 워크플로우**: 선행 `2026-11-05-office-backoffice.md`, `2026-11-04-pivot-v1-build.md`

## 요청 원문

> 같은 일을 위임하는 모임은 만들었는데, 이걸 실제 오프라인 삶의 시간으로 바꾸는
> 가장 핵심 아이디어가 준비가 안 되어 있다. 시장 조사를 통해서 가능한 것 10개를
> 실제 feasibility를 볼 수 있도록 모두 구현하라.

## 설계 결정

- **표준 전환 메커니즘 10종 확정** (id = 조사 문서 앵커 = 구현 카드, 계약):
  time-lock(잔고→ICS 캘린더 블록) / lightning(그룹+지역 번개 매칭·RSVP) /
  season(트레바리형 유료 시즌 모임 — 수익 C 실증) / partner-voucher(파트너
  바우처+수수료 — 수익 A 실증) / timebank(그룹 품앗이) / buddy(1:1 짝꿍) /
  challenge(주간 오프라인 챌린지·스트릭) / stamps(전환 실측 스탬프·레벨=Growth) /
  local-course(지역 코스 큐레이션) / gift-time(시간 선물 초대장)
- **구현 1차 면 = 백오피스(브라우저)**: 인프라 미정 상태에서 가장 빠른 검증면.
  각 카드 = 실행 버튼 + feasibility 패널(실험 흐름·측정 지표·조사 근거 링크·
  **대표 Go/보류/No-go 평가 입력**). 검증된 승자만 Python 코어로 승격.
- 조사(R)와 구현(D)은 id 계약으로 병렬 — 조사는 사례·수치·feasibility 표·실험
  지표 임계값, 구현은 전부 실동작+node 테스트.

## 처리 단계

| # | 시각 | 부문 | 수행 내용 | 산출물/링크 |
|---|------|------|-----------|-------------|
| 1 | 2026-11-05 | concierge | 10종 표준 목록·계약 확정, 병렬 핸드오프 | |
| 2 | 2026-11-05 | 상품기획(리서치) | 10종 시장 조사·feasibility 표·실험 설계 | `ops/research-movement-ideas.md` |
| 3 | 2026-11-05 | IT | office "무브먼트 실험" 탭 — 10종 전부 실동작 구현 | `docs/office.html` 외 |
| 4 | 2026-11-05 | concierge | 독립 검증 — movement_tests 27/27·parity 18/18·TC 85/85(P0 56/56, TC-MOV 10 신규)·export 멱등·문법 OK, 근거 링크를 GitHub 문서로 연결 → 커밋·푸시·라이브 확인 | |

## 확인 필요 (대표 질문)

- (완료 후) 10종 feasibility 평가 — office "무브먼트 실험" 탭에서 Go/보류/No-go
  직접 입력 요청 예정.

## 결과 요약

- **조사** (ops/research-movement-ideas.md): 종합 순위 stamps→buddy→time-lock→
  lightning→challenge→season(수익 트랙 병행 최우선)→gift-time→partner-voucher→
  local-course→timebank. A급 출처 4(Airbnb 20%·Matthews 원논문·MS Viva·듀오링고
  스트릭). 교훈: stamps가 측정 인프라(없으면 전환 실측 불가), 번개 참가는 무료
  철칙(Meetup 실패), "하버드 3% 연구"는 허구 — 인용 금지.
- **구현** (docs/office.html 무브먼트 실험 탭): 10종 전부 실동작 — ICS(RFC5545)
  다운로드·잔고 차감, 번개 매칭·RSVP·성사율, 시즌 정원·대기열·매출 집계, 바우처
  수수료 누계, 품앗이 매칭, 짝꿍 상호 확인, 챌린지 스트릭, 스탬프·레벨(대시보드
  배지 연동), 지역 코스(export_office 진실원), 시간 선물. 카드마다 실측 지표 +
  Go/보류/No-go 평가 패널(상단 요약판, JSON 내보내기 포함). 대시보드 잔고 =
  적립 − 전환으로 확장.
- **검증**: movement_tests 27/27, parity 18/18 유지, TC 85/85(P0 56/56).
- **대표 요청**: 탭에서 10종 실행해 보고 평가 입력 → 데이터 탭 JSON 내보내기로
  회수. 조사 추천과 함께 다음 집중 대상 결정.
