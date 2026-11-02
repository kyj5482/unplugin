"""큐·승인 게이트 셀프테스트 — `python3 core/selftest_queue.py` 로 실행.

임시 디렉토리에 UNPLUGIN_DATA / UNPLUGIN_FLOWS를 격리한 뒤 core를 import 한다
(core/common.py가 import 시점에 환경변수를 읽으므로 순서가 중요).
검증 항목: TC-OPS-003/004/006/007, TC-DEL-005. 끝나면 임시 디렉토리 삭제.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 격리: core import "전에" 환경변수 설정 ─────────────────
_TMP = Path(tempfile.mkdtemp(prefix="unplugin-selftest-"))
os.environ["UNPLUGIN_DATA"] = str(_TMP / "data")
os.environ["UNPLUGIN_FLOWS"] = str(_TMP / "flows")
sys.path.insert(0, str(ROOT))

from core import common, flow, queue as q  # noqa: E402  (env 설정 후 import)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}" + (f"  ← {detail}" if detail else ""))


def outbox_mails() -> list[dict]:
    if not common.OUTBOX.exists():
        return []
    return [common.parse_mail(p) for p in sorted(common.OUTBOX.glob("*.md"))]


def mails_after(n: int) -> list[dict]:
    return outbox_mails()[n:]


def items_of(state: str, customer: str) -> list[dict]:
    return [i for i in common.list_queue(state) if i["customer"] == customer]


def item_in(state: str, item_id: str) -> dict | None:
    p = common.queue_item_path(state, item_id)
    return common.read_json(p) if p.exists() else None


def new_flow(cust: str, title: str) -> str:
    return flow.create_flow(cust, title, "delegation", f"셀프테스트 요청: {title}")


def main() -> int:
    common.ensure_dirs()

    # 고객 준비: 실제 demo 프로필 복사 + 두 번째 고객(tier=flow)
    demo_src = ROOT / "data" / "customers" / "demo" / "profile.json"
    demo = json.loads(demo_src.read_text(encoding="utf-8"))
    common.write_json(common.CUSTOMERS / "demo" / "profile.json", demo)
    common.write_json(common.CUSTOMERS / "mina" / "profile.json", {
        "id": "mina", "name": "미나", "address": "mina.q9z1@unplugin.me",
        "contact": "mina@example.com", "type": "SFRA", "tier": "flow",
        "approval_limit": 30000, "deny_list": [], "trusted_senders": [],
        "onboarded": True,
    })

    # ── ① one 고객 2건 → 1건만 active, 2번째는 대기 안내(순번+업셀 1회) ──
    n0 = len(outbox_mails())
    a1 = q.enqueue("demo", "delegation", "공과금 납부 확인", new_flow("demo", "공과금 납부 확인"), amount=50000)
    n1 = len(outbox_mails())
    a2 = q.enqueue("demo", "delegation", "식당 예약 변경", new_flow("demo", "식당 예약 변경"), amount=50000)
    waits1 = [m for m in outbox_mails()[n0:n1] if "대기 안내" in m["subject"]]
    waits2 = [m for m in mails_after(n1) if "대기 안내" in m["subject"]]
    check("① 1번째 요청은 대기 안내 없음 (슬롯 여유)", len(waits1) == 0, f"{len(waits1)}통")
    check("① 2번째 요청에 대기 안내 메일 1통", len(waits2) == 1, f"{len(waits2)}통")
    body = waits2[0]["body"] if waits2 else ""
    check("① 대기 안내에 대기 순번 포함", "대기 순번: 1번째" in body)
    check("① 대기 안내에 예상 시작 시점 포함", "시작될 예정" in body)
    check("① 상위 티어 업셀 딱 1회(1문장)", body.count("Unplug Flow") == 1,
          f"{body.count('Unplug Flow')}회")
    q.run_tick()
    check("① one(슬롯1) 고객은 1건만 active",
          len(items_of("active", "demo")) == 1 and len(items_of("pending", "demo")) == 1,
          f"active={len(items_of('active', 'demo'))} pending={len(items_of('pending', 'demo'))}")
    check("① active는 먼저 접수된 건", (items_of("active", "demo") or [{}])[0].get("id") == a1)
    q.cancel(a1)
    q.cancel(a2)

    # ── ② flow(2슬롯) 고객 3건 → 2건 동시 active, 같은 고객 내 FIFO ──
    b1 = q.enqueue("mina", "delegation", "주간 장보기 1차", new_flow("mina", "주간 장보기 1차"), amount=50000)
    b2 = q.enqueue("mina", "delegation", "주간 장보기 2차", new_flow("mina", "주간 장보기 2차"), amount=50000)
    b3 = q.enqueue("mina", "delegation", "주간 장보기 3차", new_flow("mina", "주간 장보기 3차"), amount=50000)
    stats = q.run_tick()
    act = [i["id"] for i in items_of("active", "mina")]
    pen = [i["id"] for i in items_of("pending", "mina")]
    check("② flow 티어는 2건 동시 active", stats["promoted"] >= 2 and len(act) == 2,
          f"promoted={stats['promoted']} active={len(act)}")
    check("② 같은 고객 내 FIFO (먼저 접수된 2건이 active, 3번째는 대기)",
          act == [b1, b2] and pen == [b3], f"active={act} pending={pen}")
    for bid in (b1, b2, b3):
        q.cancel(bid)

    # ── ③ 한도 이내(20000 ≤ 30000) → 자동 진행 + 결제 직전 요약 step ──
    f3 = new_flow("demo", "도서 주문")
    a3 = q.enqueue("demo", "delegation", "도서 주문", f3, amount=20000, est_hours=0.5)
    q.run_tick()
    done3 = item_in("done", a3)
    flow3 = flow.flow_path(f3).read_text(encoding="utf-8")
    check("③ 한도 이내 결제는 자동 진행되어 done", done3 is not None and done3.get("charged") is True)
    check("③ Flow에 \"결제 직전 내역 요약\" step 존재",
          "결제 직전 내역 요약" in flow3 and "(한도 이내 자동 진행)" in flow3)

    # ── ④ 한도 초과(50000) → ask 1회만, approve→결제 진행, reject→결제 0 ──
    f4 = new_flow("demo", "키보드 구매")
    a4 = q.enqueue("demo", "delegation", "키보드 구매", f4, amount=50000)
    q.run_tick()
    q.run_tick()  # 두 번 tick 돌려도 재질문 없어야 함
    flow4 = flow.flow_path(f4).read_text(encoding="utf-8")
    asks4 = len(re.findall(r"\(고객\)", flow4))
    it4 = item_in("active", a4)
    check("④ 한도 초과 → ask_customer 1회만 (재질문 금지)", asks4 == 1, f"{asks4}회")
    check("④ 질문에 금액·내용·승인 방법 포함",
          "50000원" in flow4 and "키보드 구매" in flow4 and "승인 방법" in flow4)
    check("④ 아이템은 approved=None으로 active 유지(asked=True)",
          it4 is not None and it4.get("approved") is None and it4.get("asked") is True)
    q.approve(a4)
    q.run_tick()
    flow4 = flow.flow_path(f4).read_text(encoding="utf-8")
    check("④ approve 후 tick → done + 결제 진행 step",
          item_in("done", a4) is not None and "결제 진행" in flow4)
    f5 = new_flow("demo", "모니터 구매")
    a5 = q.enqueue("demo", "delegation", "모니터 구매", f5, amount=50000)
    q.run_tick()
    q.reject(a5)
    q.run_tick()
    flow5 = flow.flow_path(f5).read_text(encoding="utf-8")
    it5 = item_in("cancelled", a5)
    check("④ reject 후 tick → cancelled + 결제 0건",
          it5 is not None and "결제 진행" not in flow5 and "결제 직전" not in flow5)

    # ── ⑤ 대기 타임아웃: 통지 1회 + cancel 시 charged=False ──
    blocker = q.enqueue("demo", "delegation", "슬롯 점유용 위임", new_flow("demo", "슬롯 점유용 위임"), amount=50000)
    q.run_tick()  # blocker가 demo의 1슬롯 점유 (승인 대기)
    a6 = q.enqueue("demo", "delegation", "세탁 수거 예약", new_flow("demo", "세탁 수거 예약"))
    p6 = common.queue_item_path("pending", a6)
    it6 = common.read_json(p6)
    it6["deadline"] = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    common.write_json(p6, it6)  # deadline을 과거로 조작
    n5 = len(outbox_mails())
    s1 = q.run_tick()
    delays = [m for m in mails_after(n5) if "대기 지연 안내" in m["subject"]]
    check("⑤ deadline 경과 pending → 지연 통지 1회", s1["timeouts"] == 1 and len(delays) == 1,
          f"timeouts={s1['timeouts']} 메일={len(delays)}통")
    dbody = delays[0]["body"] if delays else ""
    check("⑤ 통지에 지연 사유·새 예상·계속/취소 선택지 포함",
          "지연 사유" in dbody and "새 예상" in dbody and "취소" in dbody and "대기" in dbody)
    s2 = q.run_tick()
    it6 = item_in("pending", a6)
    check("⑤ 재통지 없음 + 아이템 유지(notified_timeout=True)",
          s2["timeouts"] == 0 and it6 is not None and it6.get("notified_timeout") is True)
    q.cancel(a6)
    it6 = item_in("cancelled", a6)
    check("⑤ 취소 시 사용량 미차감(charged=False)",
          it6 is not None and it6.get("charged") is False)
    q.cancel(blocker)

    # ── ⑥ 사용량 80% 사전 통지 (mina: flow 40h → 32h 이상) ──
    n6 = len(outbox_mails())
    a7 = q.enqueue("mina", "delegation", "월간 정기 업무 일괄", new_flow("mina", "월간 정기 업무 일괄"), est_hours=35.0)
    q.run_tick()
    usage = common.read_json(q.usage_path("mina"))
    month = common.now().strftime("%Y-%m")
    notices = [m for m in mails_after(n6) if "80% 도달" in m["subject"]]
    check("⑥ est_hours가 월별 누적됨", usage["monthly"].get(month) == 35.0,
          f"usage={usage['monthly'].get(month)}")
    check("⑥ 한도 80% 도달 시 사전 통지 1회", len(notices) == 1 and item_in("done", a7) is not None,
          f"{len(notices)}통")
    check("⑥ 통지에 잔여 한도·선택지(대기/업그레이드) 포함",
          bool(notices) and "잔여" in notices[0]["body"] and "업그레이드" in notices[0]["body"])

    print(f"\n결과: {PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)  # 임시 격리 디렉토리 삭제
    sys.exit(code)
