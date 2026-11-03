# SETUP — 대표 맥북 실서비스 가이드

맥북에서 Unplugin v0.5를 실제로 돌리는 순서. 위에서 아래로 그대로 실행하면 된다.

## 1. 요구사항

- macOS + `python3` (맥 기본 포함 — **추가 설치 불필요, 표준 라이브러리만 사용**)
- 저장소 클론:

```bash
git clone <저장소 URL> unplugin
cd unplugin
```

## 2. 시뮬레이션 모드로 먼저 검증

실제 메일 계정을 붙이기 전에, 파일 기반 시뮬레이션으로 전체 파이프라인이 도는지 확인한다.

```bash
# 셀프테스트 전부 (mailbox / queue / dashboard / onboarding / service 등)
for f in core/selftest_*.py; do python3 "$f" || break; done

# 통합 E2E (16건)
python3 tests/e2e_runner.py

# 서비스 1사이클 — mail 단계는 "설정 없음 → skip" 로그가 정상
python3 -m core serve --once
```

셋 다 전체 PASS / exit 0 이면 준비 완료. `serve` 로그 형식:
`[HH:MM:SS] mail↓수신 처리n 큐(승격/실행/대기) mail↑발신`

## 3. 실제 이메일 연결 (v0.5 — Gmail 1계정 + 서브어드레싱)

1) **Gmail 2단계 인증 → 앱 비밀번호 발급**
   Google 계정 → 보안 → 2단계 인증 활성화 → "앱 비밀번호" → 메일용 16자리 생성
   (로그인 비밀번호가 아니라 이 앱 비밀번호를 쓴다)

2) **`secrets/mail.json` 작성** — 예시 파일을 복사해 값만 채운다.
   `secrets/` 전체가 `.gitignore`에 등록되어 있어 **커밋에서 자동 제외**된다.

```bash
cp secrets/mail.example.json secrets/mail.json
open -e secrets/mail.json   # imap_user/imap_pass/smtp_user/smtp_pass 채우기
```

3) **고객 프로필에 서브어드레싱 주소 등록**
   `data/customers/<고객id>/profile.json`에서:
   - `address` → `내계정+고객id@gmail.com` (Gmail은 `+` 뒤를 무시하고 같은 메일함으로 배달)
   - `contact` → 고객의 실제 메일 주소 (회신이 여기로 발송됨)

```json
{ "address": "unplugin.beta+jisoo@gmail.com", "contact": "지수의실제주소@gmail.com" }
```

4) **본인 폰에서 테스트**: 폰 메일 앱에서 아무 메일이나
   `내계정+고객id@gmail.com`으로 포워딩한다.

5) **서비스 기동**:

```bash
python3 -m core serve --interval 60
```

6) **확인**: 1~2사이클 안에 로그에 `mail↓1 … mail↑n`이 찍히고,
   접수/상태 **회신이 실제 메일로 도착**하면 성공.
   수동 단건 확인은 `python3 -m core mail-fetch`, `python3 -m core mail-send --dry-run`.

## 4. 실제 브라우저 실행 (선택)

큐 실행을 시뮬레이션이 아닌 실제 브라우저로 돌리려면:

```bash
pip3 install playwright && playwright install chromium
UNPLUGIN_REAL_BROWSER=1 python3 -m core serve --interval 60
```

실행 증빙 스크린샷은 `data/evidence/<큐아이템id>/`에 저장된다 — 대시보드/Flow에서 확인.

## 5. 보안 주의

- **`secrets/` 절대 커밋 금지** (`.gitignore`로 제외되지만, `git add -f` 금지)
- 승인 한도(`approval_limit`)·거부 목록(`deny_list`)은 고객 프로필에서 관리 — 한도 초과 결제는 승인 전 실행되지 않는다
- **미등록 발신자의 메일은 자동 실행되지 않는다** — `data/quarantine/`(검토함)에 격리 후 고객 확인

## 6. 상시 실행

```bash
nohup python3 -m core serve --interval 60 > service.log 2>&1 &
tail -f service.log          # 로그 확인
```

맥 재부팅 후에도 자동 시작하려면: `~/Library/LaunchAgents/`에 launchd plist를 만들어
`ProgramArguments`에 위 명령을, `RunAtLoad`/`KeepAlive`를 true로 등록한다.

## 7. 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| 로그에 `mail 수신 skip — 설정 없음(secrets/mail.json)` | config 미작성 | 3-2) 수행. 파일이 있어도 JSON 오류면 동일 — `python3 -c "import json;json.load(open('secrets/mail.json'))"`로 검증 |
| IMAP 로그인 실패 (`AUTHENTICATIONFAILED`) | 로그인 비밀번호를 넣음 / 2단계 인증 미설정 | 앱 비밀번호 재발급 후 `imap_pass`/`smtp_pass` 교체 (3-1) |
| 큐가 멈춤 — 같은 건이 계속 active/대기 | 승인 대기 중 (한도 초과 결제 등) | `python3 -m core status`로 아이템 ID 확인 → `python3 -m core approve <id>` (반려는 `reject`) |
| 메일을 보냈는데 `mail↓0` | 다른 고객 주소로 보냄 / 이미 읽음 처리됨 | 프로필 `address`와 수신 주소 일치 확인, 미읽음(UNSEEN) 상태인지 확인 |
