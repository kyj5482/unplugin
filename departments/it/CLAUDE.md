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
4. AI 브라우저 세션 연동 PoC (egolite 또는 대안, 1개 위임 업무 자동화) — queue.run_tick()의
   실행 시뮬레이션 지점을 실 실행기로 교체. 증빙 첨부(TC-DEL-010)·인젝션 방어(TC-DEL-011) 포함
5. 이메일 v0.5 — 단일 메일박스 + 서브어드레싱(`+고객id@`) IMAP 폴링 → v1 — 전용 도메인
   + Cloudflare Email Routing 캐치올 + Worker 수신, Resend/SES 발신 (상세: ops/email-channel.md)

## 운영 코어 사용법 (대표 일상 루프)

```
python3 -m core onboard tests/fixtures/onboard-demo.json   # 신규 고객
# data/inbox/ 에 메일 파일 투입 (실환경에선 IMAP이 대신)
python3 -m core mail-poll     # 수신 처리 (격리/규칙/위임 접수 + 고객 상태 메일)
python3 -m core queue-run     # 큐 1틱 (슬롯·승인 게이트·타임아웃)
python3 -m core approve <id>  # 결제 승인 (고객 회신 반영)
python3 -m core dashboard     # data/dashboard.html — 대표용 Unified View
python3 -m core kpi           # Reclaimed Hours 주간 리포트
python3 -m core status        # 한 줄 현황
```

## 산출물 위치
- 도구·스크립트: `tools/`
- 기술 검토·아키텍처 결정: `adr/YYYY-MM-DD-<slug>.md`
