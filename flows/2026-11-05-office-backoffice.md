# Flow: 백오피스 — 홈페이지에서 실제 동작하는 운영 콘솔

- **ID**: 2026-11-05-office-backoffice
- **유형**: 대표 지시
- **접수**: 2026-11-05
- **상태**: 완료 (UI 시각 확인은 대표 맥북 1회 권장)
- **관련 워크플로우**: 선행 `2026-11-04-pivot-v1-build.md`

## 요청 원문

> 개발된 서비스를 지금 제품 홈페이지에 백오피스로 구현해서 실제로 동작하도록 해줘.

## 설계 결정

- GitHub Pages는 정적 호스팅(서버 없음, 인프라 미정) → **코어 로직을 JS 엔진으로
  포팅해 브라우저에서 실행**. 데이터는 운영자 브라우저 localStorage에만 저장
  (서버 전송 없음 — 공개 URL이어도 안전), JSON 내보내기/가져오기 제공.
- core/가 단일 진실원: `core/export_office.py`가 카탈로그·스트레스 플레이북·
  그룹 테이블·데모 85통을 `docs/office-data.js`로 내보냄 — JS는 데이터를
  복제하지 않고 생성물로 받는다.
- **패리티 테스트**(tests/office_parity.js): 데모 85통을 Python 코어와 JS 엔진이
  각각 처리한 결과(고객별 합계·이벤트·매칭)가 완전 일치해야 PASS — 포팅 드리프트 방지.
- 진입: docs/office.html, 홈페이지 푸터 "운영 콘솔" 링크.

## 처리 단계

| # | 시각 | 부문 | 수행 내용 | 산출물/링크 |
|---|------|------|-----------|-------------|
| 1 | 2026-11-05 | concierge | 정적 호스팅 제약 하 아키텍처 확정(JS 포팅+localStorage+패리티) | |
| 2 | 2026-11-05 | IT | office.html SPA(7탭)·export_office·패리티 테스트·TC-OFC | `docs/office.html` 외 |
| 3 | 2026-11-05 | concierge | 푸터 진입 링크 | `docs/index.html` |
| 4 | 2026-11-05 | concierge | 독립 검증 — 패리티 18/18(고객별 합계 Python=JS 완전 일치), export 멱등, TC 75/75(P0 51/51, TC-OFC 5 신규), e2e 21/21, 문법 OK, office-data.js 59KB → 커밋·푸시·라이브 확인 | |

## 확인 필요 (대표 질문)

- (없음)

## 결과 요약

- **산출물**: docs/office.html(8탭 SPA — 대시보드/수신함/적립 피드/팁 생성기/
  커뮤니티/고객 온보딩·calibrate/미매칭 백로그/데이터), docs/office-data.js
  (core 수출 생성물), core/export_office.py, tests/office_parity.js(18/18),
  tests/e2e/office.md(TC-OFC-001~005). 홈페이지 푸터 "운영 콘솔" 진입 링크.
- **동작 보장**: JS 엔진은 Python 코어와 데모 85통 처리 결과가 고객별 합계까지
  완전 일치(뱅커스 라운딩 포함). 데이터는 브라우저 localStorage 단독(서버 전송
  없음), JSON 내보내기/가져오기.
- **다음 단계**: 카탈로그 변경 시 `python3 -m core.export_office` 재생성 루틴을
  IT 체크리스트에 추가, 기기 간 동기화는 인프라 결정 후.
