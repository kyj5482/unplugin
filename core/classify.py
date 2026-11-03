"""업무 플러그인 분류기 — 포워딩된 요청을 카탈로그의 업무 유형에 자동 매칭.

고객은 목록에서 고르지 않는다. 메일을 포워딩하면 이 분류기가:
  - 지원 업무(available/beta) → 해당 플러그인으로 바로 접수
  - 준비 중(planned) 또는 카탈로그 밖 → "신규 업무" 접수 (준비 1~3일 안내, 플러그인 백로그)

카탈로그: core/plugins/*.json (id 기준 병합 — 파일명 정렬 순, 먼저 읽은 것이 우선)
"""
from __future__ import annotations

import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent / "plugins"
_STATUS_RANK = {"available": 2, "beta": 1, "planned": 0}


def load_catalog() -> list[dict]:
    plugins: list[dict] = []
    seen: set[str] = set()
    if not PLUGIN_DIR.exists():
        return plugins
    for path in sorted(PLUGIN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for pl in data.get("plugins", []):
            pid = pl.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                plugins.append(pl)
    return plugins


def match(text: str) -> dict | None:
    """텍스트(제목+지시)에서 가장 잘 맞는 플러그인을 찾는다.

    점수 = 일치한 트리거 수. 동점이면 status 우선(available > beta > planned),
    그다음 트리거 특이도(트리거 수가 적은 플러그인이 더 특이적).
    매칭 없으면 None — 호출자는 '신규 업무'로 처리한다.
    """
    text = (text or "").lower()
    best: tuple[int, int, int] | None = None
    best_pl: dict | None = None
    best_score = 0
    for pl in load_catalog():
        triggers = pl.get("triggers", [])
        score = sum(1 for t in triggers if t.lower() in text)
        if score == 0:
            continue
        rank = (score, _STATUS_RANK.get(pl.get("status", "planned"), 0), -len(triggers))
        if best is None or rank > best:
            best, best_pl, best_score = rank, pl, score
    if best_pl is None:
        return None
    return {"plugin": best_pl, "score": best_score}


def is_supported(hit: dict | None) -> bool:
    return bool(hit) and hit["plugin"].get("status") in ("available", "beta")
