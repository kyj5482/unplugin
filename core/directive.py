"""대표 지시 처리 — "지시: ..." 입력의 전 과정 (TC-OPS-001, workflows/directive.md).

① 담당 부문 배정(키워드 라우팅) → ② 산출물을 해당 부문 디렉토리에 저장 →
③ 반환: 산출물 경로 + Flow 경로 + 맥북 확인 방법 1줄 + 다음 단계 제안 1개.

공개 인터페이스:
  handle(text) -> dict  # {"dept", "output", "flow", "check", "next"}
"""
from __future__ import annotations

from . import common, flow

_ROUTES = [
    ("product", ("문진", "추천", "요금제", "가격", "경험", "카탈로그", "설문")),
    ("marketing", ("콘텐츠", "블로그", "소셜", "후기", "스토리", "홍보")),
    ("cs", ("응대", "온보딩 진행", "피드백 수집", "고객 안내")),
    ("it", ("개발", "버그", "도구", "브라우저", "배포", "대시보드", "큐")),
]


def _route(text: str) -> str:
    low = text.lower()
    for dept, keys in _ROUTES:
        if any(k in low for k in keys):
            return dept
    return "it"


def handle(text: str) -> dict:
    """대표 지시 1건 처리. 반환 4요소는 CLI가 그대로 출력한다."""
    body = text.split(":", 1)[1].strip() if ":" in text else text.strip()
    dept = _route(body)
    fid = flow.create_flow("ops", f"지시: {body[:40]}", "대표 지시", body)
    flow.add_step(fid, "concierge", f"담당 부문 배정: {dept}", notify_customer=False)

    out_dir = common.ROOT / "departments" / dept / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{common.now():%Y-%m-%d}-{common.slug(body, 24)}.md"
    output.write_text("\n".join([
        f"# 지시 처리: {body}",
        "",
        f"- 담당: {dept}",
        f"- Flow: flows/{fid}.md",
        f"- 처리: {common.iso()}",
        "",
        "## 검토 결과 (초안)",
        "",
        f"{body} — 해당 부문 규칙(departments/{dept}/CLAUDE.md)에 따라 검토·반영안을 정리한다.",
        "다음 세션에서 이 파일을 열어 세부 내용을 채우고 대표 확인을 받는다.",
    ]), encoding="utf-8")
    flow.add_step(fid, dept, f"산출물 작성: {output.relative_to(common.ROOT)}",
                  notify_customer=False)
    flow.set_status(fid, "완료")

    return {
        "dept": dept,
        "output": str(output.relative_to(common.ROOT)),
        "flow": f"flows/{fid}.md",
        "check": f"맥북 확인: `open {output.relative_to(common.ROOT)}` (또는 에디터로 열기)",
        "next": f"다음 단계 제안: {dept} 부문 CLAUDE.md 기준으로 산출물 세부 내용을 채우고 대표 승인 받기",
    }
