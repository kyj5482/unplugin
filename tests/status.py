#!/usr/bin/env python3
"""E2E 테스트케이스 상태 집계. 사용법: python3 tests/status.py"""
import re
import sys
from pathlib import Path

E2E_DIR = Path(__file__).parent / "e2e"
TC_RE = re.compile(r"^## (TC-[A-Z]+-\d+): (.+)$")
FIELD_RE = re.compile(r"^- (상태|우선순위): (\S+)")

def parse():
    cases = []
    for path in sorted(E2E_DIR.glob("*.md")):
        current = None
        for line in path.read_text(encoding="utf-8").splitlines():
            m = TC_RE.match(line)
            if m:
                current = {"id": m.group(1), "title": m.group(2),
                           "file": path.name, "상태": "?", "우선순위": "?"}
                cases.append(current)
                continue
            if current:
                f = FIELD_RE.match(line)
                if f:
                    current[f.group(1)] = f.group(2)
    return cases

def main():
    cases = parse()
    if not cases:
        print("테스트케이스가 없습니다.")
        return 1

    width = max(len(c["title"]) for c in cases)
    for c in cases:
        mark = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⛔"}.get(c["상태"], "❓")
        print(f'{mark} {c["id"]:<12} {c["우선순위"]:<3} {c["title"]:<{width}}  ({c["file"]})')

    total = len(cases)
    passed = sum(1 for c in cases if c["상태"] == "PASS")
    p0 = [c for c in cases if c["우선순위"] == "P0"]
    p0_fail = [c for c in p0 if c["상태"] != "PASS"]
    print(f"\n전체: {passed}/{total} PASS")
    print(f"P0 (베타 필수): {len(p0) - len(p0_fail)}/{len(p0)} PASS — 잔여 {len(p0_fail)}건")
    if p0_fail:
        print("P0 잔여: " + ", ".join(c["id"] for c in p0_fail))
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
