# KPI 설계 — Reclaimed Hours (북극성 지표)

## 정의

**Reclaimed Hours** = 사용자가 디지털에 쓰던 시간 중, Unplugin에 위임되어 **실제 오프라인 활동으로 전환된** 시간.

단순히 "에이전트가 대신 한 시간"이 아니다. 전환 깔때기로 측정한다:

```
① Delegated Hours   : 위임으로 사용자 손을 떠난 디지털 시간 (문진·위임 기록 기반 추정)
        │   × 전환율
        ▼
② Reclaimed Hours   : 그 시간 중 실제 오프라인 활동에 쓰인 시간 (CS 피드백 offline_realized/reclaimed_hours)
        │   × 깊이
        ▼
③ Experience Depth  : 오프라인 경험의 질 — 오감 자극·배움 여부 (offline_story 정성 평가, 추후 점수화)
```

## 부문별 기여 지표

| 부문 | 움직이는 지표 | 어떻게 |
|---|---|---|
| CS | ①→② 전환율 | 문진으로 알맞은 위임 선택, 피드백으로 실측 |
| IT | ① 규모 | 위임 가능한 업무 범위 확대 (브라우저 세션, 자동화) |
| 상품기획 | ②, ③ | 시간·취향에 맞는 오프라인 경험 추천의 적중률 |
| 마케팅 | 신규 ① | Reclaimed Hours 숫자가 담긴 스토리로 신규 사용자 유입 |

## 측정 소스 (현 단계: 파일 기반)

- `flows/` — Delegated Hours 추정치 기록
- `departments/cs/feedback/` — `offline_realized`, `reclaimed_hours`, `offline_story`
- 집계: 추후 IT 부문이 스크립트로 자동화 (로드맵 2단계 뷰어에 포함)

## 안티 지표 (하지 않을 것)

- 체류시간·세션 수 늘리기 — 우리는 디지털 사용을 **줄이는** 회사다
- 위임 건수 자체 — 전환 없는 대행은 비서 서비스일 뿐이다
