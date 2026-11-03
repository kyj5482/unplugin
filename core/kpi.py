"""KPI — 피드백 검증·Reclaimed Hours 깔때기 집계 (ops/kpi.md).

커버 TC: FBK-001(필수 태깅 검증), FBK-002(offline_realized=no → 원인 분류·핸드오프),
FBK-003(Delegated/Reclaimed/전환율 집계 + 주간 리포트).

공개 인터페이스:
  validate_feedback(path) -> list[str]   # 누락/오류 필드 목록 (빈 리스트 = 합격)
  aggregate(feedback_dir=None) -> dict   # 집계 + ops/reports/kpi-<YYYY>-W<주차>.md 작성
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import common

REQUIRED_FIELDS = ("delegation", "satisfaction", "offline_realized", "offline_story", "reclaimed_hours")
DEFAULT_FEEDBACK_DIR = common.ROOT / "departments" / "cs" / "feedback"


def _reports_dir() -> Path:
    # 셀프테스트 격리: UNPLUGIN_REPORTS 환경변수가 있으면 그 경로 사용
    return Path(os.environ.get("UNPLUGIN_REPORTS", common.ROOT / "ops" / "reports"))


def _frontmatter(path: Path) -> dict[str, str]:
    """피드백 md의 --- 블록(key: value)을 dict로. 블록이 없으면 빈 dict."""
    raw = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", raw, re.S)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip().lower()] = v.split("#", 1)[0].strip().strip('"')
    return fields


def _num(value: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", value or "")
    return float(m.group(0)) if m else None


def validate_feedback(path) -> list[str]:
    """필수 5필드 누락·값 오류 목록 반환 (TC-FBK-001). 빈 리스트면 합격."""
    fm = _frontmatter(Path(path))
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if not fm.get(field):
            problems.append(field)
    if fm.get("satisfaction"):
        n = _num(fm["satisfaction"])
        if n is None or not (1 <= n <= 5):
            problems.append("satisfaction(1-5 범위 오류)")
    if fm.get("offline_realized") and fm["offline_realized"].lower() not in ("yes", "no", "미확인"):
        problems.append("offline_realized(yes/no/미확인 아님)")
    return problems


def classify_cause(story: str) -> str:
    """offline_realized=no 스토리에서 원인 자동 분류 (TC-FBK-002)."""
    s = story or ""
    if any(k in s for k in ("유튜브", "넷플", "폰만", "그냥 쉬", "의욕", "귀찮")):
        return "동기 부족"
    if any(k in s for k in ("멀", "거리", "이동")):
        return "추천 부적합(거리)"
    if any(k in s for k in ("짬", "파편", "짧아", "틈틈")):
        return "시간 파편화"
    if any(k in s for k in ("안 맞", "취향", "재미없")):
        return "추천 부적합(취향)"
    return "미분류"


def handoff_unrealized(feedback_dir) -> dict[str, list[dict]]:
    """offline_realized=no 피드백을 원인 태그별로 분류 (TC-FBK-002).

    cause 필드가 없으면 스토리에서 자동 분류한다.
    """
    groups: dict[str, list[dict]] = {}
    for p in sorted(Path(feedback_dir).glob("*.md")):
        fm = _frontmatter(p)
        if fm.get("offline_realized", "").lower() == "no":
            cause = fm.get("cause") or classify_cause(fm.get("offline_story", ""))
            groups.setdefault(cause, []).append({
                "file": p.name,
                "delegation": fm.get("delegation", ""),
                "story": fm.get("offline_story", ""),
            })
    return groups


def process_unrealized(feedback_dir) -> list[str]:
    """no 케이스를 원인별로 상품기획 개선 Flow로 핸드오프 (TC-FBK-002 ②).

    원인 그룹당 Flow 1건 — 중복 생성 방지를 위해 같은 날 같은 원인은 1건.
    반환: 생성된 flow id 목록.
    """
    from . import flow as flow_mod
    created = []
    for cause, items in handoff_unrealized(feedback_dir).items():
        files = ", ".join(i["file"] for i in items)
        fid = flow_mod.create_flow(
            "ops", f"오프라인 미전환 개선 — 원인 {cause}", "개선 과제",
            f"offline_realized=no {len(items)}건 (원인: {cause}) — {files}")
        flow_mod.add_step(fid, "cs",
                          f"원인 분류 완료: {cause} ({len(items)}건)",
                          handoff="cs → product: 추천 적중률 개선 — 이 케이스가 KPI의 최대 적",
                          notify_customer=False)
        created.append(fid)
    return created


def weekly_complaints(feedback_dir) -> list[dict]:
    """반복 불만 감지 — 같은 불만(complaint 태그)이 고객 2명 이상이면
    담당 부문 개선 과제 Flow 생성 (TC-FBK-004). 반환: 생성 내역."""
    from . import flow as flow_mod
    groups: dict[str, set[str]] = {}
    for p in sorted(Path(feedback_dir).glob("*.md")):
        fm = _frontmatter(p)
        tag = fm.get("complaint", "").strip()
        if tag:
            groups.setdefault(tag, set()).add(fm.get("customer", p.name))
    dept_map = {"승인": "it", "속도": "it", "지연": "it", "추천": "product",
                "메일": "it", "가격": "product", "요금": "product"}
    created = []
    for tag, customers in groups.items():
        if len(customers) < 2:
            continue
        dept = next((d for k, d in dept_map.items() if k in tag), "it")
        fid = flow_mod.create_flow(
            "ops", f"반복 불만 개선 — {tag}", "개선 과제",
            f"고객 {len(customers)}명에게서 같은 유형의 불만 접수: {tag}")
        flow_mod.add_step(fid, "cs",
                          f"반복 불만 감지: \"{tag}\" (고객 {len(customers)}명)",
                          handoff=f"cs → {dept}: 개선 과제 — 반복 불만은 구조 문제",
                          notify_customer=False)
        created.append({"tag": tag, "customers": len(customers),
                        "dept": dept, "flow": fid})
    return created


def aggregate(feedback_dir=None) -> dict:
    """Delegated/Reclaimed/전환율 집계 + 주간 리포트 작성 (TC-FBK-003)."""
    fdir = Path(feedback_dir) if feedback_dir else DEFAULT_FEEDBACK_DIR
    rows: list[dict] = []
    warnings: list[str] = []
    delegated = reclaimed = 0.0

    for p in sorted(fdir.glob("*.md")) if fdir.exists() else []:
        fm = _frontmatter(p)
        d = _num(fm.get("delegated_hours", ""))
        if d is None:
            # delegated_hours는 필수로 간주 — 없으면 추정하지 않고 스킵 + 경고
            warnings.append(f"{p.name}: delegated_hours 없음 — 집계에서 제외")
            continue
        realized = fm.get("offline_realized", "").lower()
        r = _num(fm.get("reclaimed_hours", "")) or 0.0
        if realized != "yes":
            r = 0.0  # 전환 안 된 시간은 Reclaimed에 넣지 않는다 (ops/kpi.md 안티 지표)
        delegated += d
        reclaimed += r
        rows.append({"file": p.name, "delegation": fm.get("delegation", ""),
                     "realized": fm.get("offline_realized", ""), "delegated": d, "reclaimed": r})

    conversion = round(reclaimed / delegated * 100, 1) if delegated else 0.0
    unrealized = handoff_unrealized(fdir) if fdir.exists() else {}

    # ── 주간 리포트 ──
    today = common.now()
    year, week, _ = today.isocalendar()
    rdir = _reports_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    report_path = rdir / f"kpi-{year}-W{week:02d}.md"

    lines = [
        f"# KPI 주간 리포트 — {year}-W{week:02d}",
        "",
        f"- 생성: {common.iso(today)}",
        f"- 피드백 소스: {fdir}",
        "",
        "## Reclaimed Hours 깔때기",
        "",
        f"- **Delegated Hours**: {delegated:g}",
        f"- **Reclaimed Hours**: {reclaimed:g}",
        f"- **전환율 (①→②)**: {conversion:g}%",
        "",
        "## 피드백별 내역",
        "",
        "| 파일 | 위임 | offline_realized | delegated | reclaimed |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['file']} | {row['delegation']} | {row['realized']} "
                     f"| {row['delegated']:g} | {row['reclaimed']:g} |")
    lines += ["", f"| **합계** |  |  | **{delegated:g}** | **{reclaimed:g}** |"]

    if unrealized:
        lines += ["", "## 상품기획 핸드오프 — offline_realized=no 원인 분류 (TC-FBK-002)", ""]
        for cause, items in unrealized.items():
            lines.append(f"### 원인: {cause}")
            for it in items:
                lines.append(f"- {it['file']} — 위임 \"{it['delegation']}\", 스토리: {it['story']}")
            lines.append("")
        lines.append("> 이 케이스들이 KPI의 최대 적 — 추천 적중률 개선을 위해 상품기획으로 핸드오프한다.")

    if warnings:
        lines += ["", "## 경고 (집계 제외)", ""] + [f"- {w}" for w in warnings]

    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    for w in warnings:
        print(f"[kpi] 경고: {w}")

    return {
        "delegated": round(delegated, 2),
        "reclaimed": round(reclaimed, 2),
        "conversion": conversion,
        "count": len(rows),
        "warnings": warnings,
        "unrealized": unrealized,
        "report": str(report_path),
    }
