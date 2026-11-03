"""mail_io 변환 계층 셀프테스트 — 네트워크 없이 격리 환경(/tmp)에서 검증.

실행: cd /home/coder/workspace/unplugin && python3 core/selftest_mailio.py
커버: MIME↔메일 dict 변환(한글·multipart·html·auth·thread), dry-run 발송, 설정 로드
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# ── 반드시 core import 전에 격리 경로 설정 ──────────────────
DATA = Path("/tmp/mailio-data")
os.environ["UNPLUGIN_DATA"] = str(DATA)
os.environ.pop("UNPLUGIN_MAIL_CONFIG", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
shutil.rmtree(DATA, ignore_errors=True)

from email.message import EmailMessage  # noqa: E402

from core import common, mail_io  # noqa: E402  (환경 설정 후 import)

EXAMPLE_CONFIG = ROOT / "secrets" / "mail.example.json"
_checks: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _checks.append(bool(ok))
    line = f"{'PASS' if ok else 'FAIL'}  {name}"
    if detail and not ok:
        line += f"  [{detail}]"
    print(line)


def main() -> int:
    common.ensure_dirs()

    # ── ① 한글 제목·본문 멀티파트 → mime_to_mail 라운드트립 ──
    subj = "전달: 아파트 관리비 고지서 — 11월분 확인 부탁"
    body = "이의신청 해줘.\n금액: 54000원이 지난달보다 많이 나왔어요."
    to_sub = mail_io.expand_address("unplugin.beta@gmail.com", "minseo")
    src = EmailMessage()
    src["Subject"] = subj
    src["From"] = "민서 <minseo@example.com>"
    src["To"] = f"언플러그인 <{to_sub}>"
    src["Date"] = "Mon, 03 Nov 2026 10:00:00 +0900"
    src.set_content(body, charset="utf-8")
    src.add_alternative(f"<html><body><p>{body}</p></body></html>",
                        subtype="html", charset="utf-8")
    m1 = mail_io.mime_to_mail(src.as_bytes())
    check("① 한글 멀티파트 라운드트립 — from/subject/body 보존",
          m1["from"] == "minseo@example.com" and m1["subject"] == subj
          and m1["body"] == body and m1["auth"] == "pass" and m1["thread"] == "",
          str(m1))
    check("① 서브어드레싱 to 그대로 유지 (+minseo)",
          m1["to"] == "unplugin.beta+minseo@gmail.com", m1["to"])

    # ── ② html-only 메일 → 태그 제거된 본문 ──
    h = EmailMessage()
    h["Subject"] = "가정통신문"
    h["From"] = "noreply@school.example"
    h["To"] = to_sub
    h.set_content(
        "<html><head><style>p{color:red}</style></head><body>"
        "<p>체험학습 <b>동의서</b>를 제출해&nbsp;주세요.</p><br>"
        "<script>alert(1)</script><div>기한: 11월 7일</div></body></html>",
        subtype="html", charset="utf-8")
    m2 = mail_io.mime_to_mail(h.as_bytes())
    check("② html-only → 태그·style·script 제거, 텍스트만",
          m2["body"] == "체험학습 동의서를 제출해 주세요.\n기한: 11월 7일",
          repr(m2["body"]))

    # ── ③ Authentication-Results fail → auth=fail ──
    f = EmailMessage()
    f["Subject"] = "긴급 송금 요청"
    f["From"] = "minseo@example.com"
    f["To"] = to_sub
    f["Authentication-Results"] = ("mx.google.com; spf=fail "
                                   "(sender ip mismatch) smtp.mailfrom=example.com; dkim=none")
    f.set_content("이 계좌로 입금 바랍니다.", charset="utf-8")
    m3 = mail_io.mime_to_mail(f.as_bytes())
    ok_pass = EmailMessage()
    ok_pass["Subject"] = "ok"
    ok_pass["From"] = "a@b.c"
    ok_pass["To"] = to_sub
    ok_pass["Authentication-Results"] = "mx.google.com; spf=pass; dkim=pass"
    ok_pass.set_content("x")
    m3b = mail_io.mime_to_mail(ok_pass.as_bytes())
    check("③ Authentication-Results: spf=fail → auth=fail / pass → pass",
          m3["auth"] == "fail" and m3b["auth"] == "pass",
          f"fail샘플={m3['auth']}, pass샘플={m3b['auth']}")

    # ── ④ References 의 <fid@unplugin.me> → thread 추출 ──
    r = EmailMessage()
    r["Subject"] = "Re: [Unplugin] 관리비 이의신청 · 확인 필요"
    r["From"] = "minseo@example.com"
    r["To"] = to_sub
    r["References"] = ("<zzz@mail.unplugin.me> "
                       "<2026-11-03-관리비-이의신청@unplugin.me>")
    r["In-Reply-To"] = "<zzz@mail.unplugin.me>"
    r.set_content("진행해 주세요.", charset="utf-8")
    m4 = mail_io.mime_to_mail(r.as_bytes())
    check("④ References → thread=flow id 추출 (자체 Message-ID 도메인은 무시)",
          m4["thread"] == "2026-11-03-관리비-이의신청", m4["thread"])

    # ── ⑤ mail_to_mime — 스레딩 헤더 + 한글 제목 인코딩 왕복 ──
    cfg = common.read_json(EXAMPLE_CONFIG)
    out = mail_io.mail_to_mime({
        "to": "minseo@example.com",
        "subject": "[Unplugin] 관리비 이의신청 접수 — 확인했어요 ✅",
        "thread": "2026-11-03-관리비-이의신청",
        "body": "민서님, 접수 완료했어요.",
    }, cfg)
    anchor = "<2026-11-03-관리비-이의신청@unplugin.me>"
    back = mail_io.mime_to_mail(out.as_bytes())
    check("⑤ thread 지정 시 References/In-Reply-To 포함 + 새 Message-ID",
          out["References"] == anchor and out["In-Reply-To"] == anchor
          and out["Message-ID"] and "unplugin.me>" not in out["Message-ID"].replace("mail.unplugin.me>", ""),
          f"refs={out['References']}, irt={out['In-Reply-To']}, mid={out['Message-ID']}")
    check("⑤ 한글 제목·본문 인코딩 왕복 + From=config from_addr",
          back["subject"] == "[Unplugin] 관리비 이의신청 접수 — 확인했어요 ✅"
          and back["body"] == "민서님, 접수 완료했어요."
          and back["from"] == cfg["from_addr"]
          and back["thread"] == "2026-11-03-관리비-이의신청",
          str(back))

    # ── ⑥ send_pending(dry_run) — outbox 2통 → sent/ 이동 ──
    os.environ["UNPLUGIN_MAIL_CONFIG"] = str(EXAMPLE_CONFIG)
    common.write_outbox({"to": "minseo@example.com", "subject": "접수 안내",
                         "thread": "fid-1", "body": "첫 번째"})
    common.write_outbox({"to": "minseo@example.com", "subject": "완료 안내",
                         "thread": "fid-1", "body": "두 번째"})
    n = mail_io.send_pending(dry_run=True)
    sent = sorted((common.OUTBOX / "sent").glob("*.md"))
    left = sorted(common.OUTBOX.glob("*.md"))
    check("⑥ send_pending(dry_run=True) — 반환 2, sent/ 로 2통 이동, outbox 비움",
          n == 2 and len(sent) == 2 and not left,
          f"n={n}, sent={[p.name for p in sent]}, left={[p.name for p in left]}")

    # ── ⑦ load_config — 없으면 None / 예시 파일이면 dict ──
    os.environ["UNPLUGIN_MAIL_CONFIG"] = "/tmp/mailio-data/no-such-config.json"
    none_cfg = mail_io.load_config()
    os.environ["UNPLUGIN_MAIL_CONFIG"] = str(EXAMPLE_CONFIG)
    got_cfg = mail_io.load_config()
    required = {"imap_host", "imap_user", "imap_pass",
                "smtp_host", "smtp_port", "smtp_user", "smtp_pass", "from_addr"}
    check("⑦ load_config — 파일 없으면 None, 예시 파일이면 스키마 키 전부 포함 dict",
          none_cfg is None and isinstance(got_cfg, dict)
          and required <= set(got_cfg),
          f"none={none_cfg}, keys={sorted(got_cfg or {})}")

    total, passed = len(_checks), sum(_checks)
    print(f"\n{passed}/{total} PASS" + ("" if passed == total else "  ← 실패 있음"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(DATA, ignore_errors=True)  # 끝나면 임시 격리 환경 삭제
    sys.exit(code)
