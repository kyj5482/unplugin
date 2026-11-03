# demo/ 작업 규칙 — 클로드 CLI 시연 가이드

이 디렉토리는 스트레스 업무(환불·분쟁) 100건 데모의 소유지다. 대표가 클로드
CLI에서 "데모 N번 처리해줘"라고 하면 아래 절차를 따른다.

## Step-by-Step 시연 절차

1. **선택**: `python3 -m core demo-list`에서 건을 고른다 (대표가 번호를 주면 그 번호).
2. **실행**: `python3 -m core demo-run <n> --fresh` — 격리 환경에서 전 과정이
   단계 번호와 함께 출력된다. 출력을 요약하지 말고 단계 흐름을 그대로 보여준다.
3. **검증**: 실행 후 아래 파일을 열어 결과를 확인시킨다.
   - Flow 문서: `demo/runtime/flows/*.md` (처리 단계 표 + 결과 요약)
   - 케이스: `demo/runtime/data/cases/*.json` (라운드·증빙·상태 resolved 확인)
   - 고객 상태 메일: `demo/runtime/data/outbox/*.md` (같은 스레드 타임라인)
   - 증빙: `demo/runtime/data/evidence/` (접수번호·영수증)
4. **수동 분기 시연** (대표가 원하면): `demo-run` 자동 시나리오 대신,
   `demo/emails/<n>…md`를 `demo/runtime/data/inbox/`에 복사하고
   `UNPLUGIN_DATA=demo/runtime/data UNPLUGIN_FLOWS=demo/runtime/flows` 환경에서
   `mail-poll → queue-run → (상대 회신 투입) → mail-poll → track-run`을 한 명령씩
   실행하며 각 틱의 변화를 보여준다. 상대 회신은 inbox에 메일 파일
   (`from: <상대 이메일>`, `thread: <flow id>`)을 떨어뜨리는 것으로 시뮬레이션한다.

## 규칙

- `demo/emails/`는 손으로 고치지 않는다 — `generate_emails.py`를 수정하고 재생성한다
  (100통 무결성은 `core/selftest_stress.py` STR-008이 검증).
- `demo/runtime/`은 격리 실행장이다. 실데이터(`data/`)·`flows/`를 데모로 오염시키지 않는다.
- 봇차단 유형(31~40, 일부 91~100)은 사람 개입 가이드가 발행되는 것까지가 정상 동작이다 —
  "실패"가 아니라 설계된 핸드오프임을 설명한다.
