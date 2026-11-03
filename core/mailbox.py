"""mailbox.py — 이메일 수신 파이프라인 (TC-EML-001~005).

data/inbox/ 의 메일 파일(.md, common.parse_mail 포맷)을 순서대로 처리한다:

  수신 → ① to 주소로 고객 식별 (미발급 주소 → 바운스·격리)
       → ② 발신자 신뢰 등급 (본인 > 등록 시스템 > 미등록/사칭 → 격리+고객 통지)
       → ③ 인젝션 방어 (본문 속 명령은 데이터 — 패턴 감지 시 격리+통지, 본인 발신 제외)
       → ④ 규칙 매칭 (등록 시스템): weekly 배치 / 조건 평가 / 즉시 Flow+큐
       → ⑤ 포워딩 위임 (본인): 지시 있으면 Flow+큐, 모호하면 1회 질문

보안 원칙 (ops/email-channel.md): 미등록·사칭·인젝션 메일은 자동 실행 절대 금지.
queue.py 와 동시 개발 중이므로 큐 아이템은 common 스키마로 직접 생성한다.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import classify, common, flow, notify

# 본문 속 명령은 지시가 아니라 데이터다 (TC-DEL-011 동일 방어)
INJECTION_PATTERNS = (
    "지시를 무시", "이전 지시", "ignore previous",
    "계좌로 입금", "계좌로 송금", "비밀번호를 회신",
)

_FWD_PREFIX = re.compile(r"^\s*(?:(?:fwd|fw|re|전달|회신)\s*:\s*)+", re.I)
_PCT = re.compile(r"증가율:\s*(\d+)")
_AMOUNT = re.compile(r"금액:\s*(\d+)")

CLARIFY_QUESTION = "보내주신 메일 잘 받았어요. 무엇을 도와드릴까요? 한 줄로 알려주세요."


# ── 헬퍼 ─────────────────────────────────────────────────

def _clean_subject(subject: str) -> str:
    """'Fwd:' 'Re:' '전달:' 류 접두어 제거."""
    return _FWD_PREFIX.sub("", subject).strip() or "제목 없음"


def _move_to(path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        dest = dest_dir / f"{common.ts()}-{path.name}"
    shutil.move(str(path), str(dest))
    return dest


def _has_injection(body: str) -> bool:
    low = body.lower()
    return any(p.lower() in low for p in INJECTION_PATTERNS)


def _quarantine(path: Path, mail: dict, customer: dict | None, reason: str) -> None:
    """검토함으로 격리 + (고객이 식별된 경우) 고객 통지. 자동 실행 없음."""
    _move_to(path, common.QUARANTINE)
    if customer:
        name = customer.get("name", customer["id"])
        notify.send(customer["id"], "메일 격리 안내", (
            f"{name}님, 안심하세요. 전용 주소로 온 메일 한 통을 자동 처리하지 않고 "
            f"검토함에 안전하게 보관해 두었어요.\n\n"
            f"- 보낸 사람: {mail['from']}\n"
            f"- 제목: {mail['subject']}\n"
            f"- 사유: {reason}\n\n"
            f"직접 요청하신 일이 맞다면 이 메일에 회신으로 알려주세요. "
            f"확인 전까지는 어떤 것도 실행하지 않아요."))


def _enqueue(customer_id: str, title: str, kind: str, flow_id: str, body: str) -> str:
    """common 스키마대로 pending 큐 아이템 직접 생성 (queue.py 미사용)."""
    m = _AMOUNT.search(body)
    item_id = f"{common.ts()}-{customer_id}-{common.slug(title)}"
    common.write_json(common.queue_item_path("pending", item_id), {
        "id": item_id,
        "customer": customer_id,
        "created": common.now().isoformat(),  # 마이크로초 포함 — 같은 초 접수도 FIFO 보장
        "kind": kind,
        "summary": title,
        "flow": flow_id,
        "amount": int(m.group(1)) if m else 0,
        "approved": None,
        "deadline": common.default_deadline(),
    })
    return item_id


def _batch_path(customer_id: str, rule: dict) -> Path:
    key = rule.get("when", {}).get("subject_contains") or rule.get("then", "rule")
    return common.CUSTOMERS / customer_id / "batch" / f"{common.slug(key)}.jsonl"


# ── 규칙 실행 ─────────────────────────────────────────────

def _apply_rule(path: Path, mail: dict, customer: dict, rule: dict) -> dict:
    cid = customer["id"]
    then = rule.get("then", "규칙 실행")

    # weekly 배치: 즉시 실행/메일 없이 적재만
    if rule.get("batch") == "weekly":
        bpath = _batch_path(cid, rule)
        bpath.parent.mkdir(parents=True, exist_ok=True)
        entry = {"date": mail["date"], "from": mail["from"],
                 "subject": mail["subject"], "body": mail["body"], "then": then}
        with bpath.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        path.unlink()
        return {"mail": path.name, "action": "batched",
                "detail": f"주간 배치 적재: {bpath.name}"}

    # 조건 평가: 증가율 추출 후 비교, 미충족이면 보관만 (메일 없음)
    cond = rule.get("condition")
    if cond:
        m = _PCT.search(mail["body"])
        pct = int(m.group(1)) if m else None
        met = (pct is not None and cond.get("op", ">=") == ">="
               and pct >= cond.get("value", 0))
        if not met:
            _move_to(path, common.CUSTOMERS / cid / "archive")
            return {"mail": path.name, "action": "archived",
                    "detail": f"조건 미충족(증가율 {pct}) — 보관만"}

    fid = flow.create_flow(cid, then, "이메일 규칙", mail["body"])
    _enqueue(cid, then, "rule", fid, mail["body"])
    path.unlink()
    return {"mail": path.name, "action": "rule_triggered",
            "detail": f"규칙 실행 — flow {fid}"}


# ── 포워딩 위임 ───────────────────────────────────────────

def _delegate(path: Path, mail: dict, customer: dict) -> dict:
    cid = customer["id"]
    title = _clean_subject(mail["subject"])
    # `>` 인용줄을 뺀 나머지가 고객의 지시
    instruction = "\n".join(
        l for l in mail["body"].splitlines() if not l.lstrip().startswith(">")
    ).strip()

    fid = flow.create_flow(cid, title, "고객 요청(이메일)", mail["body"])
    if instruction:
        # 위임 금지 목록(UC-A3): 고객이 "직접 하고 싶다"고 한 일은 바로 실행하지 않고 확인
        try:
            from . import onboarding
            denied = onboarding.check_deny(customer, f"{title} {instruction}")
        except ImportError:
            denied = False
        if denied:
            flow.ask_customer(
                fid, "이 일은 직접 하고 싶다고 하셨던 '위임 금지 목록'에 있어요. "
                     "그래도 이번엔 맡기시겠어요? \"진행\"이라고 회신 주시면 시작할게요.")
            path.unlink()
            return {"mail": path.name, "action": "deny_check",
                    "detail": f"금지 목록 확인 요청 — flow {fid}"}
        # 업무 플러그인 자동 분류 — 고객은 목록에서 고르지 않는다 (UC-G7)
        hit = classify.match(f"{title} {instruction}")
        if classify.is_supported(hit):
            pl = hit["plugin"]
            flow.add_step(fid, "concierge",
                          f"업무 분류: '{pl['name']}' 플러그인 ({pl['status']}) — 바로 진행합니다",
                          notify_customer=True)
            _enqueue(cid, title, f"plugin:{pl['id']}", fid, mail["body"])
            path.unlink()
            return {"mail": path.name, "action": "delegated",
                    "detail": f"위임 접수 — flow {fid} / 플러그인 {pl['id']} / 지시: {instruction[:60]}"}
        # 신규 업무 유형: 바로 실행하지 않고 상품기획·IT 검토로 — 고객에겐 준비 시간 안내
        why = "준비 중(planned)인 업무" if hit else "카탈로그에 없는 새로운 유형"
        flow.add_step(fid, "concierge", f"신규 업무 유형 접수 — {why}. 플러그인 백로그로 등록",
                      handoff="concierge → product/it: 신규 플러그인 검토·우선순위 결정",
                      notify_customer=False)
        notify.send_flow_update(
            cid, fid, flow.flow_path(fid), "접수",
            f"\"{title}\" — 새로운 유형의 업무예요",
            "이건 아직 저희가 바로 처리하도록 준비된 유형이 아니에요.\n"
            "처리 방식을 준비하는 데 보통 1~3일이 걸립니다. 준비가 끝나면 "
            "이 스레드로 알려드리고 바로 시작할게요. 그동안 요금은 차감되지 않아요.")
        path.unlink()
        return {"mail": path.name, "action": "new_type",
                "detail": f"신규 업무 접수 — flow {fid} ({why})"}

    # 지시가 비어 모호 → 회신으로 1회만 질문
    flow.ask_customer(fid, CLARIFY_QUESTION)
    path.unlink()
    return {"mail": path.name, "action": "clarify",
            "detail": f"지시 모호 — flow {fid} 에 1회 질문"}


# ── 메인 파이프라인 ──────────────────────────────────────

def _process_one(path: Path) -> dict:
    mail = common.parse_mail(path)
    sender = mail["from"].strip().lower()

    # ① 고객 식별 (수신 주소 = 고객 1:1)
    customer = common.customer_by_address(mail["to"])
    if customer is None:
        _move_to(path, common.QUARANTINE)
        return {"mail": path.name, "action": "bounce",
                "detail": f"미발급 주소 {mail['to']} — 수신 거부·격리"}

    # ② 발신자 신뢰 등급
    auth_ok = mail["auth"] == "pass"
    is_owner = auth_ok and sender == customer.get("contact", "").strip().lower()
    is_trusted = auth_ok and sender in [
        s.strip().lower() for s in customer.get("trusted_senders", [])]
    if not (is_owner or is_trusted):
        reason = ("발신자 인증 실패(사칭 의심)" if not auth_ok else "미등록 발신자")
        _quarantine(path, mail, customer, reason)
        return {"mail": path.name, "action": "quarantined",
                "detail": f"{reason} — 격리·고객 통지, 자동 실행 없음"}

    # ③ 인젝션 방어 (본인 발신 제외) — 본문 속 명령은 데이터일 뿐
    if not is_owner and _has_injection(mail["body"]):
        _quarantine(path, mail, customer, "본문 인젝션 의심 패턴 감지")
        return {"mail": path.name, "action": "quarantined",
                "detail": "본문 인젝션 의심 — 격리·고객 통지, 자동 실행 없음"}

    # ④ 규칙 매칭
    for rule in common.load_rules(customer["id"]):
        when = rule.get("when", {})
        if (when.get("from", "").strip().lower() == sender
                and when.get("subject_contains", "") in mail["subject"]):
            return _apply_rule(path, mail, customer, rule)

    # ⑤ 본인 발신·규칙 미매칭 → 포워딩 위임
    if is_owner:
        return _delegate(path, mail, customer)

    # 등록 시스템 발신인데 매칭 규칙 없음 → 자동 실행 없이 보관
    _move_to(path, common.CUSTOMERS / customer["id"] / "archive")
    return {"mail": path.name, "action": "archived",
            "detail": "등록 발신·매칭 규칙 없음 — 보관만"}


def process_inbox() -> list[dict]:
    """data/inbox/*.md 를 순서대로 처리. 메일별 결과 dict(mail, action, detail) 반환."""
    common.ensure_dirs()
    return [_process_one(p) for p in sorted(common.INBOX.glob("*.md"))]


# ── 주간 배치 요약 ────────────────────────────────────────

def process_weekly_batches(force: bool = False) -> list[dict]:
    """배치 jsonl 을 모아 고객당 주제별로 flow 1건 + 요약 메일 1통 발송 후 삭제.

    force=False 면 금요일에만 동작 (규칙: '매주 금요일 한 번에').
    """
    common.ensure_dirs()
    results: list[dict] = []
    if not force and common.now().weekday() != 4:  # 4 = 금요일
        return results

    for bpath in sorted(common.CUSTOMERS.glob("*/batch/*.jsonl")):
        cid = bpath.parent.parent.name
        entries = [json.loads(l) for l in
                   bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not entries:
            bpath.unlink()
            continue
        topic = bpath.stem
        title = f"주간 요약 — {topic} {len(entries)}건"

        fid = flow.create_flow(cid, title, "이메일 규칙(주간 배치)",
                               " / ".join(e["subject"] for e in entries))
        prof = common.load_profiles().get(cid, {})
        name = prof.get("name", cid)
        lines = [f"{name}님, 이번 주에 온 {topic} {len(entries)}건을 "
                 f"한 번에 모아 요약해 드려요.\n"]
        for e in entries:
            first = next((l.strip() for l in e["body"].splitlines() if l.strip()), "")
            lines.append(f"- {e['date'][:10]} · {e['subject']}\n  {first}")
        lines.append("\n자세히 볼 메일이 있으면 번호로 알려주세요. "
                     "나머지는 신경 쓰지 않으셔도 돼요.")
        notify.send(cid, title, "\n".join(lines), thread=fid)

        flow.add_step(fid, "concierge", f"주간 요약 {len(entries)}건 발송",
                      notify_customer=False)
        flow.set_status(fid, "완료")
        bpath.unlink()
        results.append({"customer": cid, "batch": bpath.name,
                        "action": "summarized",
                        "detail": f"{len(entries)}건 요약 1통 발송 — flow {fid}"})
    return results
