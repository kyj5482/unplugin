"""AI 에이전트 직원 조직 — 역할 기반 배정 (TC-STR-007).

회사는 1인 대표 + AI 에이전트 직원들로 운영된다. 각 직원은 역할(role)을 갖고,
큐 아이템·케이스가 생길 때 가장 한가한 해당 역할 직원에게 배정된다.
로스터: core/agents_roster.json (단일 출처). 배정 기록은 아이템/케이스의
"assignee" 필드와 Flow 단계의 부문 표기("it/rena" 형식)로 남는다.

역할:
  concierge   접수·분류·고객 커뮤니케이션 (오케스트레이터)
  resolver    일반 위임 수행 (브라우저·자동 실행)
  negotiator  상대방 이메일 협상 (환불·분쟁 멀티라운드)
  tracker     완료 추적 (환불 입금 확인·넛지)
  coordinator 사람 개입(HITL) 창구 — 직원 가이드 발행·결과 회수

공개 인터페이스:
  roster() -> list[dict]
  assign(role) -> dict            # 가장 부하가 적은 해당 역할 직원
  workload() -> dict[str, int]    # 직원별 진행 중 건수
  tag(agent) -> str               # Flow 부문 칸 표기 "dept/name"
"""
from __future__ import annotations

import json
from pathlib import Path

from . import common

ROSTER_PATH = Path(__file__).resolve().parent / "agents_roster.json"


def roster() -> list[dict]:
    return json.loads(ROSTER_PATH.read_text(encoding="utf-8"))["agents"]


def _by_role(role: str) -> list[dict]:
    return [a for a in roster() if a.get("role") == role]


def workload() -> dict[str, int]:
    """직원별 진행 중 건수 = active 큐 + 열린 케이스의 assignee 집계."""
    load: dict[str, int] = {a["id"]: 0 for a in roster()}
    for it in common.list_queue("active") + common.list_queue("pending"):
        who = it.get("assignee")
        if who in load:
            load[who] += 1
    if common.CASES.exists():
        for p in common.CASES.glob("*.json"):
            case = common.read_json(p)
            if case.get("status") not in ("resolved", "failed", "cancelled"):
                who = case.get("assignee")
                if who in load:
                    load[who] += 1
    return load


def assign(role: str) -> dict:
    """해당 역할 직원 중 부하 최소 1명. 역할이 없으면 concierge로 폴백."""
    pool = _by_role(role) or _by_role("concierge")
    load = workload()
    pool.sort(key=lambda a: (load.get(a["id"], 0), a["id"]))
    return pool[0]


def tag(agent: dict) -> str:
    """Flow 처리 단계의 부문 칸 표기: 'it/rena' — 누가 했는지까지 보인다."""
    return f"{agent.get('dept', 'it')}/{agent['id']}"
