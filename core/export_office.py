"""export_office.py — 백오피스(docs/office.html)용 데이터 수출.

core 가 단일 진실원이다: 카탈로그(분류 병합 순서 그대로)·스트레스 플레이북·
키워드 폴백·커뮤니티 테이블·측정 상수·데모 고객/메일 85통을
docs/office-data.js 로 내보낸다. 브라우저 엔진(OFFICE-PURE)은 이 데이터만 읽고
의미론은 core 와 동일하게 동작해야 한다 — 검증: node tests/office_parity.js

사용: python3 -m core.export_office   (멱등 — 같은 입력이면 같은 출력)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import classify, common, community, stress
from .dividend import (DEFAULT_BASELINE, DEFAULT_EMOTION, DEFAULT_EVIDENCE,
                       DEFAULT_THRESHOLD, REPORT_MARKER, _DONE_WORDS, _MOVEMENTS)
from .tips import PLACEHOLDER_ADDR, REPORT_LINE

OUT = common.ROOT / "docs" / "office-data.js"
DEMO = common.ROOT / "demo"


def _demo_customers() -> list[dict]:
    rows = []
    for p in sorted((DEMO / "customers").glob("*/profile.json")):
        rows.append(common.read_json(p))
    return rows


def _demo_mails() -> list[dict]:
    """demo/emails/*.md → 헤더+본문. 결정적 출력을 위해 date 는 헤더에 있을 때만."""
    mails = []
    for p in sorted((DEMO / "emails").glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
        if not m:
            continue
        headers = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        mails.append({k: headers[k] for k in ("from", "to", "subject", "date", "thread")
                      if headers.get(k)} | {"id": p.name, "body": m.group(2).strip()})
    return mails


def build() -> dict:
    return {
        "generated_note": "생성물 — python3 -m core.export_office 로 재생성",
        "constants": {
            "report_marker": REPORT_MARKER,
            "done_words": list(_DONE_WORDS),
            "default_baseline": DEFAULT_BASELINE,
            "default_emotion": DEFAULT_EMOTION,
            "default_threshold": DEFAULT_THRESHOLD,
            "default_evidence": DEFAULT_EVIDENCE,
            "report_line": REPORT_LINE,
            "placeholder_addr": PLACEHOLDER_ADDR,
            "movements": [list(m) for m in _MOVEMENTS],
            "status_rank": classify._STATUS_RANK,
            "min_group": community.MIN_GROUP,
            "digest_days": community.DIGEST_DAYS,
            "stress_group": community.STRESS_GROUP,
        },
        # 분류기와 동일한 병합 순서(00-seed 우선, id 중복 제거) — 매칭 동점 규칙에 중요
        "catalog": [
            {k: pl.get(k) for k in ("id", "name", "category", "triggers", "status",
                                     "baseline_minutes", "emotion_load", "evidence")}
            for pl in classify.load_catalog()
        ],
        "playbooks": [
            {k: pb.get(k) for k in ("id", "name", "triggers", "baseline_minutes",
                                     "emotion_load", "evidence", "opener", "escalation")}
            for pb in stress.PLAYBOOKS
        ],
        "keyword_fallback": [list(kv) for kv in stress._KEYWORD_FALLBACK],
        "group_names": community.GROUP_NAMES,
        "group_tips": community.GROUP_TIPS,
        "demo_customers": _demo_customers(),
        "demo_mails": _demo_mails(),
    }


def main() -> int:
    data = build()
    js = ("// 생성물 — python3 -m core.export_office 로 재생성 (직접 수정 금지)\n"
          "// core(파이썬)가 단일 진실원: 카탈로그·플레이북·상수·데모 데이터.\n"
          "const OFFICE_DATA = "
          + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
          + ";\n"
          "if (typeof window !== \"undefined\") window.OFFICE_DATA = OFFICE_DATA;\n"
          "if (typeof module !== \"undefined\") module.exports = OFFICE_DATA;\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"docs/office-data.js — {len(js.encode('utf-8'))/1024:.1f} KB / "
          f"카탈로그 {len(data['catalog'])} · 플레이북 {len(data['playbooks'])} · "
          f"고객 {len(data['demo_customers'])} · 메일 {len(data['demo_mails'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
