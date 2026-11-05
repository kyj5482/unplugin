# E2E 테스트케이스 — 브라우저 백오피스 (OFC)

제품 홈페이지(docs/office.html)의 백오피스는 core(파이썬)의 측정 의미론을
JS(OFFICE-PURE 블록)로 포팅해 브라우저에서 동작한다. 데이터 단일 진실원은
core — `python3 -m core.export_office` 가 docs/office-data.js 를 재생성한다.
검증 러너: `node tests/office_parity.js` (파이썬 기대값과 교차 비교).

## TC-OFC-001: 코어↔브라우저 엔진 패리티
- 상태: PASS
- 검증 기록: tests/office_parity.js (2026-11-05) — 데모 85통을 양쪽에서 처리,
  고객 5명 전원 saved/감정/적립/매칭/미매칭/제안/팁 완전 일치 + 스트레스 가중
  (환불 120분·감정 5 / 보증금 150분), pyRound(뱅커스), 팁 프롬프트 스냅샷 2건
  문자열 일치
- 우선순위: P0
- 유스케이스: 백오피스 측정 신뢰성

**Given** 같은 데모 메일 85통과 고객 프로필 5건이 있다
**When** core(파이썬) 파이프라인과 office.html 의 OFFICE-PURE 엔진이 각각 처리하면
**Then** 고객별 절약 분·감정·적립 건수·매칭/미매칭·무브먼트 제안 횟수·팁 회신 수가
완전히 일치하고, 개인 보정 반올림(뱅커스)과 팁 프롬프트 문자열도 동일하다
- 검증: node tests/office_parity.js 전부 PASS

## TC-OFC-002: 수신함 라우팅 — 보고·포워딩·격리
- 상태: PASS
- 검증 기록: tests/office_parity.js (2026-11-05) — 데모 85통에서 보고 적립 65건·
  팁 회신 20건, 합성 케이스로 미발급 주소 bounce·미등록 발신 quarantined 확인
- 우선순위: P0

**Given** 전용 주소로 메일이 수신된다
**When** 백오피스 수신함이 처리하면
**Then** ① [보고]/완료 키워드 + 본인·신뢰 발신 → 자동 적립 ② 본인 포워딩(비보고)
→ 팁 카드 회신 ③ 미발급 주소 → bounce ④ 미등록 발신 → 격리로 분기된다
- 검증: office_parity.js 수신 분기 케이스

## TC-OFC-003: 온보딩·개인 보정(calibrate)
- 상태: PASS
- 검증 기록: tests/office_parity.js (2026-11-05) — slug 전용주소
  `<id>.<4자리>@unplugin.me` 형식, clampFactor 0.5~2.0 클램프·비수치 1.0 폴백
- 우선순위: P1

**Given** Admin이 고객 탭에서 이름으로 온보딩하거나 보정 계수를 바꾼다
**When** 온보딩/calibrate 를 실행하면
**Then** 전용주소가 자동 발급되고, time_factor 는 0.5~2.0 으로 클램프되어
이후 적립(기준치 × 보정, 뱅커스 반올림)에 반영된다
- 검증: office_parity.js 온보딩·보정 케이스 + 지속성 케이스(×1.2 → 108분)

## TC-OFC-004: 커뮤니티 — 그룹·모임 제안·다이제스트 주기
- 상태: PASS
- 검증 기록: tests/office_parity.js (2026-11-05) — 데모 처리 후 같은 그룹+같은
  지역 ≥2 고객에 모임 섹션 ≥2건 생성, 다이제스트 강제 발송 직후 비강제 재실행은
  전건 "주기 미도래"로 0통
- 우선순위: P1

**Given** 적립 이력으로 커뮤니티 그룹이 편성되어 있다
**When** 무브먼트 제안과 다이제스트를 실행하면
**Then** 같은 그룹+같은 지역 2인 이상이면 제안 메일에 모임 섹션이 붙고,
다이제스트는 그룹당 7일에 1회만 발송된다 (멤버는 익명 닉네임으로만 표기)
- 검증: office_parity.js 커뮤니티 케이스

## TC-OFC-005: 데이터 지속성 — localStorage 왕복
- 상태: PASS
- 검증 기록: tests/office_parity.js (2026-11-05) — localStorage 모킹으로 저장→
  복원 후 잔고(108분)와 임계치 연속성(216분 도달 시 제안) 유지, office.html 이
  키 unplugin-office-v1 에 저장함을 확인
- 우선순위: P1

**Given** 백오피스에서 적립이 진행된 상태다
**When** 브라우저를 닫았다가 다시 열면(저장→복원)
**Then** 고객·잔고·커뮤니티 상태가 그대로 복원되고, 이후 적립의 임계치 판정이
이어진다 (서버 전송은 없다 — localStorage 단독)
- 검증: office_parity.js 지속성 케이스

# 무브먼트 실험 10종 (MOV) — docs/office.html "무브먼트 실험" 탭

오프라인 전환 메커니즘 10종. 각 카드에 [실행해보기] + feasibility 패널(흐름·
실측 지표·근거 링크 ops/research-movement-ideas.md#<id>·대표 Go/보류/No-go 평가,
localStorage 저장). 순수 로직은 [MOVEMENT-PURE] 블록, 러너: `node tests/movement_tests.js`.

## TC-MOV-001: time-lock — 잔고를 .ics 일정으로 전환·차감
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — RFC5545 필수 필드·CRLF,
  다음 토요일 슬롯, 차감 후 잔고·ledger.movements 기록·스탬프, 잔고 부족 거부
- 우선순위: P0

**Given** 고객 잔고(적립−전환)가 N분 이상이다
**When** N분·무브먼트 라벨로 타임락을 실행하면
**Then** 유효한 .ics(주말 기본 슬롯, "되찾은 시간 — <라벨>")가 생성·다운로드되고
잔고에서 N분이 차감 기록된다 (부족하면 차감 없이 거부)

## TC-MOV-002: lightning — 같은 그룹+지역 자동 매칭 번개
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 같은 그룹·같은 region ≥2만
  제안, 활성 제안 중복 방지, RSVP 2명 성사·성사율, 장소 후보 = 지역 코스
- 우선순위: P0

**Given** 같은 커뮤니티 그룹에 같은 지역 고객이 2명 이상이다
**When** 번개 제안을 생성하고 멤버가 RSVP 하면
**Then** 초대 문안과 일시·장소 후보가 생성되고, 수락 2명이면 성사되어
타임락 ICS 연계(참석자 90분 차감)로 이어진다

## TC-MOV-003: season — 유료 시즌 모임 (수익 C)
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 회차 4~8·가격 10~25만 클램프,
  정원 초과 대기열, 중복 신청 거부, 매출 = 가격 × 확정 인원
- 우선순위: P0

**Given** 시즌 모임(이름·회차·가격·정원)을 개설한다
**When** 고객이 신청하면
**Then** 정원까지 확정·초과는 대기열로 관리되고 예상 매출이 집계된다

## TC-MOV-004: partner-voucher — 파트너 바우처·수수료 (수익 A)
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 수수료 15~20% 클램프,
  자격 = 잔고 ≥ 임계치, 발급 중복 방지, 사용 시 수수료 집계(8만 원×20%=1.6만)
- 우선순위: P0

**Given** 지역 파트너(공방·클래스)가 등록되어 있다
**When** 잔고 임계치 도달 고객에게 바우처를 발급하고 사용 처리하면
**Then** 설정 수수료(15~20%)가 계산되어 수수료 누계에 집계된다

## TC-MOV-005: timebank — 그룹 품앗이 보드
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 본인 제공↔요청 매칭 거부,
  성사 시 양쪽 교환 기록(스탬프), 매칭된 항목 재매칭 방지
- 우선순위: P1

**Given** 그룹 멤버가 제공/요청을 등록했다
**When** 제공↔요청을 매칭하면
**Then** 양쪽에 교환이 기록되고 같은 항목은 다시 매칭되지 않는다

## TC-MOV-006: buddy — 2인 짝꿍 상호 약속
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 같은 그룹 2인 짝·자기쌍 없음,
  한쪽 확인만으로 미완료, 양쪽 확인 → 완료+양쪽 스탬프, 활성 쌍 중복 매칭 방지
- 우선순위: P1

**Given** 같은 그룹에 짝이 없는 멤버가 2명 이상이다
**When** 짝꿍 매칭 후 약속(무브먼트+날짜)을 정하고 양쪽이 확인하면
**Then** 쌍이 완료 처리되고 양쪽에 실행 스탬프가 찍힌다

## TC-MOV-007: challenge — 주간 챌린지·스트릭
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 같은 날 중복 인증 거부,
  연속 3일 스트릭, 공백 시 스트릭 리셋
- 우선순위: P1

**Given** 주간 오프라인 챌린지에 참여자가 있다
**When** 날짜별로 인증 체크하면
**Then** 중복 인증은 거부되고 연속 일수 기준 스트릭이 집계된다

## TC-MOV-008: stamps — 실행 실측·레벨 (Growth)
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 타임락·번개·바우처·품앗이·
  짝꿍·챌린지·선물 실행 시 자동 스탬프, 레벨 경계(1/3/6/10) — 대시보드 카드에
  레벨 배지 연동(office.html dash)
- 우선순위: P0

**Given** 무브먼트 실험들이 실제 실행된다
**When** 실행 이벤트가 발생하면
**Then** 고객별 스탬프가 자동 기록되고 개수 구간별 레벨이 대시보드에 표시된다

## TC-MOV-009: local-course — 지역 코스 추천
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 고객 region(성수동) 코스 3종
  매칭, 코스 데이터는 core/export_office.py LOCAL_COURSES 단일 진실원
- 우선순위: P1

**Given** 고객 프로필에 region 이 있다
**When** 동네 코스를 조회하면
**Then** 해당 지역의 산책로·시장·공방 카드가 추천되고 버튼으로 타임락(ICS+차감)에 연결된다

## TC-MOV-010: gift-time — 잔고를 지인 초대장으로
- 상태: PASS
- 검증 기록: tests/movement_tests.js (2026-11-05) — 차감 후 잔고 일치, 초대 문안
  ("<이름>님께"), ICS SUMMARY "선물한 시간" 포함
- 우선순위: P1

**Given** 고객 잔고가 선물할 분 이상이다
**When** 지인 이름·분을 정해 시간 선물을 실행하면
**Then** 초대 문안 + 캘린더 초대(.ics)가 생성되고 잔고에서 차감 기록된다
