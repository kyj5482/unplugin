"""mail_io.py — 실제 메일박스 연동 (v0.5: 단일 계정 + 서브어드레싱).

ops/email-channel.md 로드맵 2단계: Gmail 등 계정 1개로
`계정+고객id@gmail.com` 서브어드레싱을 사용해 베타 고객 실검증.

구조 원칙 — 네트워크와 변환의 분리:
- 변환 계층 (네트워크 불필요, selftest_mailio.py 커버):
    mime_to_mail(raw_bytes) : 수신 MIME → common 메일 dict
    mail_to_mime(mail)      : outbox 메일 dict → EmailMessage
    expand_address(...)     : 서브어드레싱 주소 생성
    load_config()           : secrets/mail.json 로드 (없으면 None → 시뮬레이션 모드)
- 네트워크 계층 (얇게 유지, 예외는 삼켜 서비스 루프 보호):
    fetch_new()    : IMAP UNSEEN → common.INBOX/*.md (mailbox.process_inbox 가 처리)
    send_pending() : common.OUTBOX/*.md → SMTP 발송 → outbox/sent/ 이동

표준 라이브러리만 사용 (imaplib, smtplib, email).
"""
from __future__ import annotations

import email
import email.header
import email.policy
import email.utils
import html as _html
import imaplib
import os
import re
import shutil
import smtplib
import ssl
from email.contentmanager import raw_data_manager
from email.message import EmailMessage, Message
from pathlib import Path

from . import common

# 우리가 보낸 스레딩 앵커: <flow-id@unplugin.me>
# (자체 Message-ID 는 @mail.unplugin.me 도메인을 써서 이 패턴과 충돌하지 않는다)
_THREAD_RE = re.compile(r"<([^<>@\s]+)@unplugin\.me>")
_MSGID_DOMAIN = "mail.unplugin.me"

# 한글 메일 대응: 선언 charset 실패 시 순서대로 재시도
_FALLBACK_ENCODINGS = ("utf-8", "euc-kr", "cp949")


# ── 설정 ─────────────────────────────────────────────────

def load_config() -> dict | None:
    """메일 계정 설정 로드. 없으면 None → 호출측은 파일 시뮬레이션 모드로 동작.

    경로: env UNPLUGIN_MAIL_CONFIG > common.ROOT/secrets/mail.json
    스키마: {"imap_host","imap_user","imap_pass",
             "smtp_host","smtp_port","smtp_user","smtp_pass","from_addr"}
    """
    path = Path(os.environ.get("UNPLUGIN_MAIL_CONFIG")
                or common.ROOT / "secrets" / "mail.json")
    if not path.exists():
        return None
    try:
        return common.read_json(path)
    except Exception as e:  # 깨진 설정 = 설정 없음 (서비스는 계속)
        print(f"[mail_io] 경고: 메일 설정 읽기 실패({path}) — {e}")
        return None


def expand_address(base: str, customer_id: str) -> str:
    """서브어드레싱 주소 생성: ("a@b.com", "minseo") → "a+minseo@b.com"."""
    local, _, domain = base.partition("@")
    return f"{local}+{customer_id}@{domain}"


# ── 디코딩 헬퍼 ───────────────────────────────────────────

def _decode_header(value) -> str:
    """RFC2047 인코딩 헤더 → str (한글 utf-8/euc-kr/cp949 대응)."""
    if value is None:
        return ""
    chunks: list[str] = []
    for data, enc in email.header.decode_header(str(value)):
        if isinstance(data, str):
            chunks.append(data)
            continue
        candidates = ([enc] if enc else []) + list(_FALLBACK_ENCODINGS)
        for e in candidates:
            try:
                chunks.append(data.decode(e))
                break
            except (LookupError, UnicodeDecodeError):
                continue
        else:
            chunks.append(data.decode("utf-8", "replace"))
    return "".join(chunks).strip()


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    declared = part.get_content_charset()
    candidates = ([declared] if declared else []) + list(_FALLBACK_ENCODINGS)
    for e in candidates:
        try:
            return payload.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", "replace")


def _strip_html(text: str) -> str:
    """text/plain 이 없을 때의 최소 변환 — 태그 제거 + 엔티티 해제."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text).replace("\xa0", " ")  # &nbsp; → 일반 공백
    lines = [l.strip() for l in text.splitlines()]
    return "\n".join(l for l in lines if l).strip()


def _extract_body(msg: Message) -> str:
    """multipart에서 text/plain 우선, 없으면 text/html 태그 제거본."""
    if msg.is_multipart():
        plain = html_part = None
        for part in msg.walk():
            if part.is_multipart():
                continue
            if "attachment" in str(part.get("Content-Disposition", "")).lower():
                continue
            ct = part.get_content_type()
            if ct == "text/plain" and plain is None:
                plain = part
            elif ct == "text/html" and html_part is None:
                html_part = part
        if plain is not None:
            return _part_text(plain).strip()
        if html_part is not None:
            return _strip_html(_part_text(html_part))
        return ""
    if msg.get_content_type() == "text/html":
        return _strip_html(_part_text(msg))
    return _part_text(msg).strip()


def _extract_thread(msg: Message) -> str:
    """References/In-Reply-To 에서 우리 스레딩 앵커 <fid@unplugin.me> 의 fid 추출."""
    for h in ("References", "In-Reply-To"):
        m = _THREAD_RE.search(_decode_header(msg.get(h)))
        if m:
            return m.group(1)
    return ""


def _extract_auth(msg: Message) -> str:
    """Authentication-Results → pass|fail.

    fail 흔적이 있으면 fail(보수적), spf=pass/dkim=pass 면 pass.
    헤더 자체가 없으면 pass — 자기 메일박스(Gmail 수신함)를 신뢰한다.
    """
    header = " ".join(str(v) for v in msg.get_all("Authentication-Results", []))
    if not header:
        return "pass"
    low = header.lower()
    if "fail" in low:
        return "fail"
    if "spf=pass" in low or "dkim=pass" in low:
        return "pass"
    return "pass"


def _extract_date(msg: Message) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date"))
        if dt is not None:
            return dt.isoformat(timespec="seconds")
    except (TypeError, ValueError):
        pass
    return common.iso()


# ── 변환: MIME ↔ common 메일 dict ────────────────────────

def mime_to_mail(raw_bytes: bytes) -> dict:
    """수신 원문(bytes) → common 메일 dict (parse_mail 과 같은 키).

    to 는 실제 수신 주소 그대로 — 서브어드레싱(`계정+고객id@...`)이 보존되어
    mailbox 파이프라인이 수신 주소로 고객을 식별할 수 있다.
    """
    msg = email.message_from_bytes(raw_bytes)
    return {
        "from": email.utils.parseaddr(_decode_header(msg.get("From")))[1],
        "to": email.utils.parseaddr(_decode_header(msg.get("To")))[1],
        "subject": _decode_header(msg.get("Subject")),
        "date": _extract_date(msg),
        "thread": _extract_thread(msg),
        "auth": _extract_auth(msg),
        "body": _extract_body(msg),
    }


def mail_to_mime(mail: dict, config: dict | None = None) -> EmailMessage:
    """outbox 메일 dict → 발송용 EmailMessage (제목·본문 UTF-8).

    스레딩: mail["thread"](=flow id)가 있으면 References/In-Reply-To 에
    <thread@unplugin.me> 를 넣어 수신측 메일앱이 같은 스레드로 묶는다.
    Message-ID 는 매번 새로 생성 (@mail.unplugin.me — 앵커 패턴과 분리).

    주의: policy.default 는 한글 제목 폴딩 시 인코딩 단어 경계의 공백을
    유실한다(CPython 리폴딩 버그) → compat32 + email.header.Header 로
    무손실 RFC2047 인코딩을 직접 수행한다 (selftest ⑤가 왕복 검증).
    """
    cfg = config if config is not None else (load_config() or {})
    msg = EmailMessage(policy=email.policy.compat32)
    msg["Subject"] = email.header.Header(mail.get("subject", ""), "utf-8")
    from_addr = cfg.get("from_addr") or mail.get("from", "")
    if from_addr:
        msg["From"] = from_addr
    msg["To"] = mail.get("to", "")
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=_MSGID_DOMAIN)
    thread = (mail.get("thread") or "").strip()
    if thread:
        anchor = f"<{thread}@unplugin.me>"
        msg["References"] = anchor
        msg["In-Reply-To"] = anchor
    # base64 CTE: 8BITMIME 미지원 서버에서도 한글 본문 안전
    msg.set_content(mail.get("body", ""), charset="utf-8", cte="base64",
                    content_manager=raw_data_manager)
    return msg


def _format_inbox_file(mail: dict) -> str:
    """common.format_mail + auth 가 fail 이면 헤더 보존 (파이프라인 ② 사칭 방어용).

    format_mail 은 auth 키를 쓰지 않고 parse_mail 기본값이 pass 이므로,
    fail 만 명시적으로 남기면 왕복 손실이 없다.
    """
    text = common.format_mail(mail)
    if mail.get("auth") and mail["auth"] != "pass":
        head, sep, rest = text.partition("\n---\n")
        text = f"{head}\nauth: {mail['auth']}{sep}{rest}"
    return text


# ── 네트워크: 수신 (IMAP) ─────────────────────────────────

def fetch_new(limit: int = 20) -> int:
    """IMAP INBOX 의 UNSEEN 메일을 common.INBOX/*.md 로 저장. 반환: 가져온 수.

    설정이 없으면 0 (시뮬레이션 모드). 예외는 경고만 출력 — 서비스 루프 보호.
    처리 자체는 기존 mailbox.process_inbox() 가 파일 기반 그대로 수행한다.
    """
    config = load_config()
    if not config:
        return 0
    count = 0
    try:
        common.ensure_dirs()
        with imaplib.IMAP4_SSL(config["imap_host"]) as imap:
            imap.login(config["imap_user"], config["imap_pass"])
            imap.select("INBOX")
            typ, data = imap.search(None, "UNSEEN")
            if typ != "OK":
                return 0
            for num in data[0].split()[:limit]:
                typ, fetched = imap.fetch(num, "(BODY.PEEK[])")
                if typ != "OK" or not fetched or fetched[0] is None:
                    continue
                mail = mime_to_mail(fetched[0][1])
                stamp = common.now().strftime("%Y%m%d-%H%M%S-%f")
                path = common.INBOX / f"{stamp}-{common.slug(mail['subject'])}.md"
                path.write_text(_format_inbox_file(mail), encoding="utf-8")
                imap.store(num, "+FLAGS", "\\Seen")  # 저장 성공 후에만 읽음 처리
                count += 1
    except Exception as e:
        print(f"[mail_io] 경고: IMAP 수신 실패 — {e}")
        return count if count else 0
    return count


# ── 네트워크: 발신 (SMTP) ─────────────────────────────────

def _smtp_connect(config: dict) -> smtplib.SMTP:
    host = config["smtp_host"]
    port = int(config.get("smtp_port", 465))
    ctx = ssl.create_default_context()
    if port == 587:
        smtp = smtplib.SMTP(host, port, timeout=30)
        smtp.starttls(context=ctx)
    else:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
    smtp.login(config["smtp_user"], config["smtp_pass"])
    return smtp


def send_pending(dry_run: bool = False) -> int:
    """common.OUTBOX 의 미발송 *.md 를 SMTP 발송 후 outbox/sent/ 로 이동.

    반환: 처리(발송+이동)한 수. 설정 없으면 0. dry_run=True 면 발송만 생략.
    개별 파일 실패는 건너뛰고 계속 — 한 통 때문에 큐가 멈추지 않는다.
    """
    config = load_config()
    if not config:
        return 0
    common.ensure_dirs()
    files = sorted(common.OUTBOX.glob("*.md"))  # sent/ 하위는 glob 비매칭
    if not files:
        return 0
    sent_dir = common.OUTBOX / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)

    smtp = None
    if not dry_run:
        try:
            smtp = _smtp_connect(config)
        except Exception as e:
            print(f"[mail_io] 경고: SMTP 접속 실패 — {e}")
            return 0

    count = 0
    try:
        for path in files:
            try:
                mail = common.parse_mail(path)
                msg = mail_to_mime(mail, config)
                if smtp is not None:
                    smtp.send_message(msg)
                dest = sent_dir / path.name
                if dest.exists():
                    dest = sent_dir / f"{common.ts()}-{path.name}"
                shutil.move(str(path), str(dest))
                count += 1
            except Exception as e:
                print(f"[mail_io] 경고: {path.name} 발송 실패 — 건너뜀 ({e})")
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass
    return count
