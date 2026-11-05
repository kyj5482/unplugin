# demo/ — 피벗 데모: 시간 배당 여정 (고객 5명 · 메일 85통)

Unplugin은 일을 대신하지 않는다. 이 데모는 피벗(2026-11-04) 모델의 전 과정을
격리 환경에서 시연한다: **포워딩→팁 카드 → (에이전트가 일하고) 보고 수신→자동
적립(산정 근거 포함) → 임계치→무브먼트 제안(+동네 모임) → 커뮤니티 다이제스트
→ Admin 운영판**. 수동 기록은 어디에도 없다.

## 구성

```
demo/
├── customers/         # 고객 5명 프로필 (지역·time_factor·trusted_senders 다양)
├── emails/            # 메일 85통 — [보고] 60 / 포워딩 20 / 미매칭 보고 5
├── index.json         # 매니페스트 (여정 5건 + 메일 목록)
├── generate_emails.py # 결정적 재생성기 (손으로 고치지 말 것)
├── legacy/            # 피벗 전 스트레스 데모 100통 (동결 — --legacy 로 재생)
├── runtime/           # 격리 실행장 (git 미추적)
└── CLAUDE.md          # 클로드 CLI 시연 절차
```

## 빠른 시작

```bash
python3 -m core demo-list          # 여정 5건 목록
python3 -m core demo-run 1 --fresh # 지수(성수동, ×1.0)의 여정 — 7단계 출력
open demo/runtime/data/admin.html  # Admin 운영판 확인
python3 -m core demo-run 7 --legacy --fresh  # (참고) 동결된 대행 경로 재생
```

고객마다 지역(성수동/망원동/판교)과 개인 보정 계수(×0.8~×1.5)가 달라,
같은 업무도 사람에 따라 적립이 달라지는 것(TC-ADM-002)과 같은 동네 이웃이
있을 때만 모임 제안이 붙는 것(TC-CMU-002)을 비교해 볼 수 있다.
