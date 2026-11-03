"""마케팅 콘텐츠 파이프라인 — 실데이터 기반 3막 스토리 (TC-MKT-001~003).

원칙:
  · 실데이터(피드백의 offline_story + reclaimed_hours)가 없으면 가상 스토리를
    쓰지 않고 거부한다 — 대안으로 대표 자가 베타 경험담을 제안 (TC-MKT-002)
  · 초안은 3막 구조(위임 전 일상 → 위임 → 오프라인 장면), Reclaimed 숫자 포함
  · 게시(published/)는 대표 승인 후에만 — 승인 없는 게시 시도는 차단 (TC-MKT-001)
  · 초안에는 고객 이름·동네·직장 등 식별 정보가 제거/치환된다 (TC-MKT-003)

공개 인터페이스:
  write_story(feedback_path) -> dict   # {"ok", "draft"|"reason"+"alternative"}
  publish(draft_path, approved=False) -> dict
  anonymize(text) -> str
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, kpi

DRAFTS = common.ROOT / "departments" / "marketing" / "drafts"
PUBLISHED = common.ROOT / "departments" / "marketing" / "published"

# 동네·기관 식별 패턴 (예: "성수동", "OO초등학교", "OO회사")
_PLACE_RE = re.compile(r"[가-힣]{1,6}(동|구|시|읍|면)\b")
_ORG_RE = re.compile(r"[가-힣A-Za-z]{2,10}(초등학교|중학교|고등학교|대학교|회사|병원)")


def anonymize(text: str) -> str:
    """고객 이름(프로필 전수)·동네·기관명을 제거/치환 (TC-MKT-003)."""
    out = text or ""
    for prof in common.load_profiles().values():
        name = prof.get("name", "")
        if name and name in out:
            out = out.replace(name, "고객 A")
    out = _PLACE_RE.sub("동네", out)
    out = _ORG_RE.sub("근처 기관", out)
    return out


def write_story(feedback_path=None, feedback_dir=None) -> dict:
    """피드백 1건으로 3막 초안 생성. 실데이터 없으면 거부 + 대안 제안."""
    # 소재 선택: 경로 직접 지정 또는 디렉토리에서 스토리 있는 첫 건
    path = None
    if feedback_path and Path(feedback_path).exists():
        path = Path(feedback_path)
    elif feedback_dir and Path(feedback_dir).exists():
        for p in sorted(Path(feedback_dir).glob("*.md")):
            fm = kpi._frontmatter(p)
            if fm.get("offline_story") and kpi._num(fm.get("reclaimed_hours", "")):
                path = p
                break
    if path is None:
        return {"ok": False,
                "reason": "flows/와 feedback/에 사용 데이터가 없어 가상 스토리를 쓰지 않습니다.",
                "alternative": "대표의 자가 베타 경험담을 먼저 작성해 소재로 쓰는 것을 제안합니다."}

    fm = kpi._frontmatter(path)
    story = fm.get("offline_story", "")
    reclaimed = kpi._num(fm.get("reclaimed_hours", ""))
    if not story or not reclaimed:
        return {"ok": False,
                "reason": f"{path.name}: offline_story 또는 reclaimed_hours가 없어 소재로 쓸 수 없습니다.",
                "alternative": "대표의 자가 베타 경험담 작성을 제안합니다."}

    delegation = fm.get("delegation", "디지털 잡무")
    safe_story = anonymize(story)
    DRAFTS.mkdir(parents=True, exist_ok=True)
    draft = DRAFTS / f"{common.ts()}-{common.slug(delegation, 20)}.md"
    draft.write_text("\n".join([
        f"# 되찾은 {reclaimed:g}시간 — {anonymize(delegation)} 이야기",
        "",
        "status: draft (대표 승인 전 — published/ 이동 금지)",
        f"source: {path.name}",
        "",
        "## 1막 — 위임 전 일상",
        f"매주 {anonymize(delegation)}에 묶여 있던 화면 앞의 시간. 끝나도 끝난 것 같지 않은 일들.",
        "",
        "## 2막 — 위임",
        f"메일 한 통을 포워딩하는 것으로 {anonymize(delegation)}이(가) 손을 떠났다. "
        f"진행 상황은 같은 메일 스레드로만 확인했다.",
        "",
        "## 3막 — 오프라인 장면",
        f"{safe_story}",
        "",
        f"**이렇게 되찾은 시간, 이번 주 {reclaimed:g}시간.**",
    ]), encoding="utf-8")
    return {"ok": True, "draft": str(draft), "reclaimed": reclaimed}


def publish(draft_path, approved: bool = False) -> dict:
    """대표 승인 후에만 published/ 이동 — 승인 없으면 차단 (TC-MKT-001 ③)."""
    p = Path(draft_path)
    if not p.exists():
        return {"ok": False, "reason": f"초안 없음: {draft_path}"}
    if not approved:
        return {"ok": False, "reason": "대표 승인 전에는 게시할 수 없어요. "
                                       "승인 후 approved=True(또는 --approved)로 다시 실행하세요."}
    PUBLISHED.mkdir(parents=True, exist_ok=True)
    dest = PUBLISHED / p.name
    text = p.read_text(encoding="utf-8").replace(
        "status: draft (대표 승인 전 — published/ 이동 금지)",
        f"status: published ({common.iso()})")
    dest.write_text(text, encoding="utf-8")
    p.unlink()
    return {"ok": True, "published": str(dest)}
