# IT 부문 CLAUDE.md

이 파일은 IT 부문의 실무 규칙이다. 이 부문은 이 디렉토리 안에서 독립적으로 진화한다.

## 책임
1. 부문 에이전트·내부 툴·서비스 개발 (바이브코딩으로 점진 개발)
2. AI 브라우저(egolite 등) 다중 세션 연동: 고객 위임 업무를 브라우저 세션으로 대행하는 실행 계층
3. 큐 기반 요청 처리 시스템: 요청 큐 → 세션 할당 → 결과 반환 (동시 세션 수 = 과금 단위)
4. 회사 홈페이지(`docs/`) 유지보수 — 정적 사이트, GitHub Pages 배포

## 개발 원칙
- **로컬 우선**: 인프라 미정. 모든 것은 대표의 맥북에서 `실행 → 확인` 가능해야 한다. 외부 서비스 의존은 대표 승인 후에만 추가.
- **한 단계씩**: 큰 시스템을 한 번에 만들지 않는다. 각 단계는 독립적으로 데모 가능해야 한다.
- **부문 소유권 존중**: 다른 부문용 도구를 만들면 해당 부문 디렉토리에 두고, 사용법을 그 부문 CLAUDE.md에 추가하도록 핸드오프한다.

## 로드맵 (한 단계씩 검증)
1. ~~저장소·홈페이지 스캐폴딩~~ (완료)
2. ~~슬라이드형 홈페이지 + 언플러그 타입 테스트 웹 구현 (docs/)~~ (완료 — 실측 데이터 교체는 남음)
3. ~~운영 코어 v0 (`core/`)~~ (완료 2026-11-02 — 이메일 파이프라인·큐·승인 게이트·Flow 상태 메일·
   대시보드·온보딩·KPI. 통합 검증: `python3 tests/e2e_runner.py` 15/15, 모듈: `core/selftest_*.py` 57건)
4. ~~실행기 구조 전환 (`core/executor.py`)~~ (완료 2026-11-03 — 큐 실행 지점을 교체형 실행기로.
   맥북에서 `pip3 install playwright` + `UNPLUGIN_REAL_BROWSER=1`이면 실제 Chromium 수행 + 증빙
   스크린샷(data/evidence/). **맥북 실증과 플러그인별 실행 스크립트 확충은 남음** — TC-DEL 계열)
5. ~~이메일 v0.5 (`core/mail_io.py`) + 서비스 데몬 (`core/service.py`)~~ (완료 2026-11-03 —
   IMAP 수신/SMTP 발신·스레딩 헤더·서브어드레싱, `python3 -m core serve`. **Gmail 계정 연결 실증은
   SETUP.md 따라 대표가 수행**) → v1 — 전용 도메인 + Cloudflare Email Routing (ops/email-channel.md)
6. ~~스트레스 케이스 엔진 + AI 에이전트 조직~~ (완료 2026-11-03 — 환불·분쟁·해지 10유형
   플레이북(`core/stress.py`), 케이스 수명주기(`cases.py`), 이메일 협상 멀티라운드(`negotiation.py`),
   egolite 어댑터·포털 레지스트리(`egolite.py`/`portals.json`), 봇차단→사람 개입 가이드(`hitl.py`),
   입금 확인까지 완료 추적(`tracking.py`), 직원 로스터·배정(`agents.py`), 데모 100통 + 단계별
   실행(`demo/`, `python3 -m core demo-run <n>`). TC 53/53 PASS. **egolite 실세션
   (UNPLUGIN_EGOLITE_URL) 연결과 맥북 실브라우저 실증은 남음** — TC-STR-004 재검증)

## 운영 코어 사용법 (대표 일상 루프)

```
python3 -m core onboard tests/fixtures/onboard-demo.json   # 신규 고객
# data/inbox/ 에 메일 파일 투입 (실환경에선 IMAP이 대신)
python3 -m core mail-poll     # 수신 처리 (격리/규칙/위임/케이스 접수 + 고객 상태 메일)
python3 -m core queue-run     # 큐 1틱 (스트레스 우선·슬롯·승인 게이트·타임아웃)
python3 -m core track-run     # 완료 추적 1틱 (환불 입금 확인·넛지·에스컬레이션)
python3 -m core cases         # 열린 환불·분쟁 케이스 현황
python3 -m core hitl-list     # 사람이 처리해야 할 일 (클릭 가이드)
python3 -m core hitl-done <id> --note "..." --confirmation "접수번호"
python3 -m core approve <id>  # 결제 승인 (고객 회신 반영)
python3 -m core agents        # AI 에이전트 직원 부하 현황
python3 -m core dashboard     # data/dashboard.html — 대표용 Unified View
python3 -m core kpi           # Reclaimed Hours 주간 리포트
python3 -m core status        # 한 줄 현황
python3 -m core demo-run <n>  # 데모 100통 중 1건 단계별 시연 (격리 환경)
```

## 산출물 위치
- 도구·스크립트: `tools/`
- 기술 검토·아키텍처 결정: `adr/YYYY-MM-DD-<slug>.md`
