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
| `onboarding.py` + `kpi.py` | 프로필 생성(타입·금지목록·한도), 금지 필터, 피드백 검증·KPI 집계 | ONB-001/003, FBK-001/003 |
| `cli.py` + `__main__.py` | `python3 -m core <cmd>` 진입점 | — |

## CLI (구현 후)

```
python3 -m core onboard <json파일>   # 고객 프로필 생성
python3 -m core mail-poll            # data/inbox/ 처리 (수신 시뮬레이션)
python3 -m core queue-run            # 큐 1틱 처리 (슬롯 배분·타임아웃 점검)
python3 -m core kpi                  # 주간 KPI 리포트 생성
python3 -m core dashboard            # data/dashboard.html 생성
```

## 데이터 레이아웃 (런타임, git 제외 — 샘플만 커밋)

```
data/
├── customers/<id>/profile.json, rules.json
├── inbox/      ← 메일 파일(.md)을 떨어뜨리면 수신됨
├── outbox/     ← 에이전트 → 고객 발신 (상태 메일 포함)
├── quarantine/ ← 미등록·사칭·인젝션 격리 (검토함)
└── queue/pending|active|done|cancelled/
```

## 메일 기반 흐름 가시성 (핵심 UX)

고객은 **메일만 봐도 자기 일의 전체 흐름을 안다**: 접수·단계 진행·확인 요청·완료 시마다
같은 스레드(thread=Flow ID)로 상태 메일이 발송되고, 각 메일 하단에 지금까지의 타임라인이
포함된다. 구현: `notify.py`, 테스트: TC-EML-006.
