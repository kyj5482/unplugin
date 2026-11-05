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
