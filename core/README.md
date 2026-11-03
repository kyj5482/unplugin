# core/ — Unplugin v0 운영 코어 (로컬·파일 기반·stdlib only)

대표 맥북에서 `python3`만으로 실제 서비스 흐름을 돌리는 v0 구현.
공용 계약(경로·메일 포맷·스키마)은 **`common.py`가 단일 출처** — 모든 모듈은 이를 import 한다.

## 모듈 소유권

| 모듈 | 책임 | 커버 TC |
|---|---|---|
| `common.py` | 경로·메일 파싱/작성·프로필·큐 IO (수정 금지, 계약) | — |
| `mailbox.py` | 수신 파이프라인: 고객 식별→발신자 검증→규칙 매칭→격리/접수 | EML-001~005 |
| `queue.py` + `approval.py` | 티어 슬롯 큐, FIFO, 승인 게이트(한도), 대기 타임아웃 | OPS-003/004/007, DEL-005 |
| `flow.py` + `notify.py` + `dashboard.py` | Flow 생성·단계 기록·완결, **단계마다 고객에게 상태 메일**(타임라인 포함), 로컬 HTML 대시보드 | OPS-002, EML-006 |
| `onboarding.py` + `kpi.py` | 프로필 생성·부분 온보딩 이어하기, 금지 필터, 피드백 검증·KPI·원인 분류·반복 불만 | ONB-001~006, FBK-001~004 |
| `stress.py` + `cases.py` | 스트레스 유형(환불·분쟁 10종) 플레이북·인텐트 추출·케이스 수명주기 | STR-001/002 |
| `negotiation.py` | 상대방 이메일 협상 멀티라운드(요구→재제시→통첩→에스컬레이션) | STR-003 |
| `egolite.py` + `portals.json` | AI 브라우저 어댑터(egolite/playwright/시뮬) — 포털 수행·봇차단·인젝션 감지 | STR-004, DEL-011 |
| `hitl.py` | 사람 개입 — 클릭 단위 가이드 발행·완료 보고·Takeover(기록 중지) | STR-005, DEL-012 |
| `tracking.py` | 완료 추적 — 입금 확인 전 완결 금지, 기한 넛지, 포털 재확인 | STR-006, DEL-010 |
| `agents.py` + `agents_roster.json` | AI 에이전트 직원 조직 — 역할 기반 배정·부하 분산 | STR-007 |
| `executor.py` | 수행 계층 — 장보기/예약/탐색 시뮬 + egolite 라우팅 + 증빙 | DEL-001~004/010 |
| `policy.py` / `recommend.py` / `recurring.py` / `billing.py` / `marketing.py` / `directive.py` | 범위 밖 거절 / 오프라인 추천·재문진 / 반복 위임 / 해지 환불 / 콘텐츠 / 대표 지시 | DEL-007/013, OFF-001~004, OPS-001/005, MKT-001~003 |
| `demo.py` + `demo/` | 데모 100통 + 격리 환경 단계별 실행 (`demo-run`) | STR-008 |
| `cli.py` + `__main__.py` | `python3 -m core <cmd>` 진입점 | — |

## CLI (구현 후)

```
python3 -m core onboard <json파일>   # 고객 프로필 생성
python3 -m core mail-poll            # data/inbox/ 처리 (수신 시뮬레이션)
python3 -m core queue-run            # 큐 1틱 처리 (슬롯 배분·타임아웃 점검)
python3 -m core track-run            # 완료 추적 1틱 (환불 입금 확인·넛지)
python3 -m core cases                # 스트레스 케이스(환불·분쟁) 목록
python3 -m core agents               # AI 에이전트 직원 로스터·부하
python3 -m core hitl-list / hitl-done <id> --note "..." --confirmation "..."
python3 -m core directive "지시: ..." # 대표 지시 처리
python3 -m core demo-list / demo-run <n>   # 데모 100통 · 단계별 시연
python3 -m core kpi                  # 주간 KPI 리포트 생성
python3 -m core dashboard            # data/dashboard.html 생성
```

## 데이터 레이아웃 (런타임, git 제외 — 샘플만 커밋)

```
data/
├── customers/<id>/profile.json, rules.json, recurring.json
├── inbox/      ← 메일 파일(.md)을 떨어뜨리면 수신됨
├── outbox/     ← 에이전트 → 고객 발신 (상태 메일 포함)
├── quarantine/ ← 미등록·사칭·인젝션 격리 (검토함)
├── cases/      ← 스트레스 케이스(환불·분쟁) — 입금 확인까지의 수명주기
├── handoff/    ← 사람 개입(HITL) 가이드·상태
├── evidence/   ← 수행 증빙 (영수증·접수번호·스크린샷)
└── queue/pending|active|done|cancelled/
```

## 메일 기반 흐름 가시성 (핵심 UX)

고객은 **메일만 봐도 자기 일의 전체 흐름을 안다**: 접수·단계 진행·확인 요청·완료 시마다
같은 스레드(thread=Flow ID)로 상태 메일이 발송되고, 각 메일 하단에 지금까지의 타임라인이
포함된다. 구현: `notify.py`, 테스트: TC-EML-006.
