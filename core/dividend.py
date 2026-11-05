"""dividend.py — 시간 배당 잔고 (측정 v0, 피벗 2026-11-04 · ops/pivot-2026-11-04.md).

우리는 일을 대신하지 않는다. 사용자가 Muze 등 범용 에이전트에 일을 시킬 때
"끝나면 <전용주소>로 제목에 [보고]를 붙여 완료 보고 메일을 보내줘" 한 줄을
붙이면(팁 카드가 항상 이 줄을 포함한다 — core/tips.py), 보고 메일이 도착하는
순간 이 모듈이 **자동으로** 절약 시간·아낀 감정을 적립한다.

절대 원칙: 수동 입력 경로는 없다. 적립은 보고 메일 수신으로만 일어난다.

측정 규칙:
  - 유형 매칭: core/classify.py → 플러그인의 baseline_minutes(직접 할 때 소요 분)
    · emotion_load(감정 부하 1~5). 미매칭이면 기본값(30분/2)으로 적립하되 기록.
  - 스트레스 유형(core/stress.py — 환불·분쟁 등)은 감정 가중: 시간보다 감정 절약이 크다.
  - 잔고가 임계치(profile.movement_threshold_minutes, 기본 180분)를 넘을 때마다
    넥스트 무브먼트(관계·배움·오감) 제안 1통 — 같은 구간에서 중복 발송 금지.

저장: data/dividend/<customer>/ledger.json
  { "customer", "totals": {saved_minutes, emotion_saved, events_count},
    "last_suggested_at_minutes", "events": [...] }
"""
from __future__ import annotations

from pathlib import Path

from . import classify, common, notify, stress

REPORT_MARKER = "[보고]"
_DONE_WORDS = ("완료", "처리했", "처리됐", "끝냈", "끝났", "마쳤", "해결했",
               "done", "completed", "finished")
DEFAULT_BASELINE = 30   # 미매칭 보고 기본 적립(분)
DEFAULT_EMOTION = 2
DEFAULT_THRESHOLD = 180  # 무브먼트 제안 임계치(분)

# 무브먼트 3축 — 상품기획 카탈로그 연결 전의 v0 제안 템플릿
_MOVEMENTS = [
    ("관계", "미뤄뒀던 사람에게 먼저 연락해 만남을 잡아보세요 — 밥 한 끼, 산책 한 번이면 충분해요."),
    ("배움", "좋아서 배워보고 싶었던 것의 원데이 클래스를 하나 예약해 보세요 — 공방, 요리, 악기 뭐든요."),
    ("오감", "화면 없이 감각을 쓰는 한 시간 — 시장 구경, 동네 새 길 산책, 손으로 만드는 일이 좋아요."),
]


# ── 잔고 파일 ─────────────────────────────────────────────

def ledger_path(customer_id: str) -> Path:
    return common.DATA / "dividend" / customer_id / "ledger.json"


def load_ledger(customer_id: str) -> dict:
    p = ledger_path(customer_id)
    if p.exists():
        return common.read_json(p)
    return {"customer": customer_id,
            "totals": {"saved_minutes": 0, "emotion_saved": 0, "events_count": 0},
            "last_suggested_at_minutes": 0,
            "events": []}


# ── 보고 메일 판정 ────────────────────────────────────────

def is_report(mail: dict) -> bool:
    """완료 보고 메일인가 — 제목 [보고] 마커 1순위, 없으면 완료 키워드 휴리스틱.

    진행 중 스레드 회신(thread 지정)은 마커가 없는 한 보고로 보지 않는다 —
    "입금 확인" 같은 대화 회신을 적립으로 오인하지 않기 위함.
    """
    if REPORT_MARKER in mail.get("subject", ""):
        return True
    if mail.get("thread"):
        return False
    low = (mail.get("body", "") or "").lower()
    return any(w in low for w in _DONE_WORDS)


# ── 적립 ─────────────────────────────────────────────────

def emotion_dots(load: int) -> str:
    load = min(max(int(load), 0), 5)
    return "●" * load + "○" * (5 - load)


DEFAULT_EVIDENCE = "ops/research-time-baselines.md#기본값"


def clamp_factor(f) -> float:
    """개인 보정 계수 — 사람마다 같은 일에 걸리는 시간이 다르다 (0.5~2.0)."""
    try:
        return min(2.0, max(0.5, float(f)))
    except (TypeError, ValueError):
        return 1.0


def _match_task(text: str) -> dict:
    """보고 본문 → 업무 유형·기준치·근거. 스트레스 유형은 감정 가중."""
    hit = classify.match(text)
    pb = stress.detect(text)
    if hit:
        pl = hit["plugin"]
        task, plugin_id, matched = pl["name"], pl["id"], True
        minutes = int(pl.get("baseline_minutes", DEFAULT_BASELINE))
        emotion = int(pl.get("emotion_load", DEFAULT_EMOTION))
        evidence = pl.get("evidence", DEFAULT_EVIDENCE)
    else:
        task, plugin_id, matched = "", None, False
        minutes, emotion = DEFAULT_BASELINE, DEFAULT_EMOTION
        evidence = DEFAULT_EVIDENCE
    if pb:  # 환불·분쟁류 — 시간보다 감정을 아낀 일. 유형별 조사 권장값 적용
        task = task or pb["name"]
        plugin_id = plugin_id or f"stress:{pb['id']}"
        minutes = max(minutes, int(pb.get("baseline_minutes", 90)))
        emotion = max(emotion, int(pb.get("emotion_load", 4)))
        evidence = pb.get("evidence", evidence)
    return {"task": task, "plugin_id": plugin_id, "matched": matched,
            "saved_minutes": minutes, "emotion_load": emotion, "evidence": evidence}


def accrue(customer_id: str, mail: dict) -> dict:
    """보고 메일 1통 → 자동 적립 + 적립 확인 메일 + (임계치 도달 시) 무브먼트 제안.

    반환: {saved_minutes, emotion_load, matched, total_saved_minutes, suggested}
    """
    subject = mail.get("subject", "").replace(REPORT_MARKER, " ").strip()
    text = f"{subject} {mail.get('body', '')}"
    m = _match_task(text)
    task = m["task"] or (subject[:40] or "이름 없는 일")

    # 개인 보정 — 같은 일도 사람마다 걸리는 시간이 다르다 (Admin이 calibrate로 조정)
    prof = common.load_profiles().get(customer_id, {})
    factor = clamp_factor(prof.get("time_factor", 1.0))
    saved = max(1, round(m["saved_minutes"] * factor))

    ledger = load_ledger(customer_id)
    event = {
        "id": f"{common.ts()}-{common.slug(task)}",
        "date": mail.get("date", common.iso()),
        "task": task,
        "plugin": m["plugin_id"],
        "matched": m["matched"],
        "saved_minutes": saved,
        "emotion_load": m["emotion_load"],
        "basis": {"baseline": m["saved_minutes"], "factor": factor,
                  "evidence": m["evidence"]},
        "subject": common.mask_sensitive(subject),
        "from": mail.get("from", ""),
    }
    ledger["events"].append(event)
    t = ledger["totals"]
    t["saved_minutes"] += saved
    t["emotion_saved"] += m["emotion_load"]
    t["events_count"] += 1

    # 적립 확인 메일 — 고객은 아무것도 기록하지 않았는데 숫자가 쌓인다
    h, mm = divmod(t["saved_minutes"], 60)
    factor_txt = "" if factor == 1.0 else f" × 개인 보정 ×{factor:g}"
    notify.send(
        customer_id,
        f"시간 배당 적립: {task} · +{saved}분",
        (f"{task} · +{saved}분 · 감정 {emotion_dots(m['emotion_load'])}\n"
         f"누적 잔고: {h}시간 {mm}분 (아낀 감정 {t['emotion_saved']})\n\n"
         "이 적립은 에이전트의 완료 보고 메일에서 자동 계산됐어요 — "
         "직접 기록하실 건 없어요.\n"
         f"산정 근거: 업무 유형 기준치 {m['saved_minutes']}분{factor_txt} — "
         f"출처 {m['evidence']}"),
        thread=f"dividend-{customer_id}")

    # 임계치 — 같은 구간 중복 제안 금지
    suggested = _maybe_suggest(customer_id, ledger)
    common.write_json(ledger_path(customer_id), ledger)
    return {"saved_minutes": saved, "emotion_load": m["emotion_load"],
            "matched": m["matched"], "total_saved_minutes": t["saved_minutes"],
            "suggested": suggested}


def _maybe_suggest(customer_id: str, ledger: dict) -> bool:
    prof = common.load_profiles().get(customer_id, {})
    threshold = int(prof.get("movement_threshold_minutes", DEFAULT_THRESHOLD))
    total = ledger["totals"]["saved_minutes"]
    if total // threshold <= ledger.get("last_suggested_at_minutes", 0) // threshold:
        return False
    ledger["last_suggested_at_minutes"] = total
    h, mm = divmod(total, 60)
    lines = [f"쌓인 시간 배당이 {h}시간 {mm}분이 됐어요. "
             "잔고에 잠들게 두지 말고, 다음 무브먼트에 투자해 보세요:\n"]
    lines += [f"- **{axis}** — {desc}" for axis, desc in _MOVEMENTS]
    # 커뮤니티 연계 — 같은 일을 위임하는 동네 이웃이 있으면 함께 움직이자고 제안
    from . import community
    meetup = community.meetup_section(customer_id, ledger)
    if meetup:
        lines.append("")
        lines.append(meetup)
    lines.append("\n하나를 고르셨다면 이 메일에 회신으로 알려주세요 — "
                 "다녀온 이야기가 다음 추천을 더 좋게 만들어요.")
    notify.send(customer_id,
                f"잔고 {h}시간 {mm}분 — 다음 무브먼트를 고를 시간이에요",
                "\n".join(lines), thread=f"dividend-{customer_id}")
    return True


# ── 조회 (CLI) ────────────────────────────────────────────

def summary(customer_id: str) -> str:
    ledger = load_ledger(customer_id)
    t = ledger["totals"]
    h, mm = divmod(t["saved_minutes"], 60)
    lines = [f"[{customer_id}] 시간 배당 잔고: {h}시간 {mm}분 · "
             f"아낀 감정 {t['emotion_saved']} · 적립 {t['events_count']}건"]
    for e in ledger["events"][-5:]:
        mark = "" if e["matched"] else " (유형 미매칭 — 기본값)"
        lines.append(f"  · {e['date'][:10]} {e['task']} +{e['saved_minutes']}분 "
                     f"감정 {emotion_dots(e['emotion_load'])}{mark}")
    if not ledger["events"]:
        lines.append("  · 아직 적립이 없어요 — 팁 카드의 [보고] 한 줄이 적립의 시작이에요.")
    return "\n".join(lines)


def all_customers() -> list[str]:
    base = common.DATA / "dividend"
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "ledger.json").exists())
