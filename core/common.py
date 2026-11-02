"""Unplugin v0 공용 모듈 — 모든 core 모듈이 공유하는 경로·포맷·헬퍼.

설계 원칙: 표준 라이브러리만 사용 (대표 맥북에서 pip 없이 실행).
메일 파일 포맷: `---` 로 감싼 key: value 헤더 + 빈 줄 + 본문 (마크다운).
기계 데이터(프로필·규칙·큐)는 JSON.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 디렉토리 ──────────────────────────────────────────────
# 셀프테스트 격리: UNPLUGIN_DATA / UNPLUGIN_FLOWS 환경변수로 경로 오버라이드 가능
DATA = Path(os.environ.get("UNPLUGIN_DATA", ROOT / "data"))
CUSTOMERS = DATA / "customers"          # <id>/profile.json, <id>/rules.json
INBOX = DATA / "inbox"                  # 수신 시뮬레이션 (.md 메일 파일 투입)
OUTBOX = DATA / "outbox"                # 발신 시뮬레이션 (에이전트 → 고객)
QUARANTINE = DATA / "quarantine"        # 미등록·사칭 발신 격리 (검토함)
QUEUE = DATA / "queue"                  # pending/ active/ done/ cancelled/
FLOWS = Path(os.environ.get("UNPLUGIN_FLOWS", ROOT / "flows"))  # Flow 문서 (Unified View)
DASHBOARD = DATA / "dashboard.html"     # 로컬 Flow 대시보드 (고객 데이터 포함 → 비공개)

QUEUE_STATES = ("pending", "active", "done", "cancelled")
TIER_SLOTS = {"one": 1, "flow": 2, "life": 4}

def ensure_dirs() -> None:
    for d in [CUSTOMERS, INBOX, OUTBOX, QUARANTINE, *(QUEUE / s for s in QUEUE_STATES)]:
        d.mkdir(parents=True, exist_ok=True)

# ── 시간/ID ──────────────────────────────────────────────
def now() -> datetime:
    return datetime.now()

def ts(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y%m%d-%H%M%S")

def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")

def slug(text: str, maxlen: int = 32) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w가-힣]+", "-", text).strip("-").lower()
    return text[:maxlen] or "item"

# ── JSON IO ──────────────────────────────────────────────
def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write_json(path: Path, obj: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# ── 메일 파일 포맷 ────────────────────────────────────────
# ---
# from: a@b.c
# to: x@unplugin.me
# subject: 제목
# date: 2026-11-02T10:00:00   (없으면 파싱 시 현재 시각)
# thread: flow-id 또는 임의 스레드 키 (선택)
# auth: pass | fail           (SPF/DKIM 시뮬레이션, 기본 pass)
# ---
# 본문 (마크다운)

def parse_mail(path: Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if not m:
        raise ValueError(f"메일 헤더 형식 오류: {path}")
    headers: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip().strip('"')
    return {
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", iso()),
        "thread": headers.get("thread", ""),
        "auth": headers.get("auth", "pass"),
        "body": m.group(2).strip(),
        "path": str(path),
    }

def format_mail(mail: dict) -> str:
    lines = ["---"]
    for k in ("from", "to", "subject", "date", "thread"):
        if mail.get(k):
            lines.append(f"{k}: {mail[k]}")
    lines += ["---", "", mail.get("body", "").rstrip(), ""]
    return "\n".join(lines)

def write_outbox(mail: dict) -> Path:
    """고객에게 가는 메일을 outbox에 기록. 반환: 파일 경로."""
    ensure_dirs()
    mail.setdefault("from", "agent@unplugin.me")
    mail.setdefault("date", iso())
    # 마이크로초 포함 → 같은 초에 여러 통이어도 파일명 정렬 = 발송 순서
    stamp = now().strftime("%Y%m%d-%H%M%S-%f")
    path = OUTBOX / f"{stamp}-{slug(mail.get('subject', 'mail'))}.md"
    path.write_text(format_mail(mail), encoding="utf-8")
    return path

# ── 고객 프로필 ───────────────────────────────────────────
# data/customers/<id>/profile.json 스키마:
# { "id": "jisoo", "name": "지수", "address": "jisoo.k7x2@unplugin.me",
#   "contact": "jisoo@example.com", "type": "SFRA", "tier": "one",
#   "approval_limit": 30000, "deny_list": ["뉴스레터 읽기"],
#   "trusted_senders": ["noreply@school.example"], "onboarded": true }
# data/customers/<id>/rules.json 스키마: {"rules": [ {"when": {"from": ..,
#   "subject_contains": ..}, "then": "...", "batch": "weekly|none"} ]}

def load_profiles() -> dict[str, dict]:
    profiles = {}
    if CUSTOMERS.exists():
        for p in CUSTOMERS.glob("*/profile.json"):
            prof = read_json(p)
            profiles[prof["id"]] = prof
    return profiles

def customer_by_address(addr: str) -> dict | None:
    addr = addr.strip().lower()
    for prof in load_profiles().values():
        if prof.get("address", "").lower() == addr:
            return prof
        if addr in [a.lower() for a in prof.get("aliases", [])]:
            return prof
    return None

def load_rules(customer_id: str) -> list[dict]:
    p = CUSTOMERS / customer_id / "rules.json"
    return read_json(p).get("rules", []) if p.exists() else []

# ── 큐 아이템 ────────────────────────────────────────────
# data/queue/<state>/<id>.json 스키마:
# { "id": "20261102-100000-jisoo-xxx", "customer": "jisoo", "created": iso,
#   "kind": "delegation|rule|recommendation", "summary": "...",
#   "flow": "flows/....md", "amount": 0, "approved": null|true|false,
#   "deadline": iso (대기 타임아웃 기준) }

def queue_item_path(state: str, item_id: str) -> Path:
    return QUEUE / state / f"{item_id}.json"

def list_queue(state: str) -> list[dict]:
    d = QUEUE / state
    if not d.exists():
        return []
    return sorted((read_json(p) for p in d.glob("*.json")), key=lambda x: x["created"])

def move_queue_item(item: dict, from_state: str, to_state: str) -> None:
    src = queue_item_path(from_state, item["id"])
    write_json(queue_item_path(to_state, item["id"]), item)
    if src.exists():
        src.unlink()

def default_deadline(hours: int = 24) -> str:
    return iso(now() + timedelta(hours=hours))
