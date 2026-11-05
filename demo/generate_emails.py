#!/usr/bin/env python3
"""피벗 데모 데이터 생성기 — 고객 5명 × 에이전트 5종 × 업무 유형의 메일 세트.

사용: python3 demo/generate_emails.py
산출:
  demo/customers/<cid>/profile.json  — 고객 5명 (지역·time_factor·trusted_senders 다양화)
  demo/emails/NNN-<kind>-<cid>.md    — [보고] 완료 메일 60통 + 포워딩 20통 + 미매칭 보고 5통
  demo/index.json                    — 매니페스트 (journeys 5건 + emails 85통)

메일은 core/common.py 포맷(--- 헤더 ---). 보고 발신은 trusted_senders에 등록된
에이전트 주소(Muze/Dots/ChatGPT/Claude/Gemini)를 순환한다. 본문에는 카탈로그
트리거가 포함되어 classify가 올바른 유형으로 적립한다. 결정적(난수 없음).
구 스트레스 데모 100통은 demo/legacy/ (demo-run --legacy)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_DIR = ROOT / "demo"
EMAILS = DEMO_DIR / "emails"
CUSTOMERS = DEMO_DIR / "customers"

AGENTS = [("Muze", "muze@agentmail.example"),
          ("Dots", "dots@agentmail.example"),
          ("ChatGPT", "chatgpt@agentmail.example"),
          ("Claude", "claude@agentmail.example"),
          ("Gemini", "gemini@agentmail.example")]

# 고객 5명 — region 3곳, time_factor 다양화 (개인 보정 시연)
PEOPLE = [
    ("jisoo", "지수", "성수동", 1.0),
    ("minho", "민호", "성수동", 1.2),
    ("sora",  "소라", "망원동", 0.8),
    ("yuna",  "유나", "망원동", 1.0),
    ("doyun", "도윤", "판교",   1.5),
]

# (제목 요지, 본문 — 카탈로그/스트레스 트리거 포함, 완료 서술)
REPORT_TASKS = [
    ("생필품 정기 주문", "요청하신 생수와 생필품 정기 주문을 쿠팡에서 완료했어. 다음 주문은 재고 기준으로 잡아뒀어."),
    ("가족 식당 예약", "토요일 저녁 식당 예약 완료했어. 예약 확정 문자도 받아뒀어."),
    ("통신 요금 이의신청", "요금 이의신청 접수하고 과오납 환불 입금까지 확인 완료했어. 부당 청구 금액은 환급됐어."),
    ("구독 해지", "안 쓰는 OTT 구독 해지 완료, 미사용분 환불 신청까지 끝냈어."),
    ("주민등록 등본 발급", "정부24에서 등본 발급 완료했어. 파일로 저장해뒀어."),
    ("가정통신문 요약", "이번 주 가정통신문 요약 완료 — 준비물 2건, 회신 마감 1건이야."),
    ("정수기 AS 접수", "정수기 수리 AS 접수 완료, 기사 방문 일정은 목요일로 확정했어."),
    ("건강검진 예약", "건강검진 예약 완료했어. 공복 조건이랑 주차 안내도 확인했어."),
    ("항공권 검색", "항공권 가격 비교해서 제일 싼 일정으로 예약 완료했어."),
    ("환불 분쟁", "환불 거부하던 업체에 환불 요구 재제시해서 결국 환불 입금 확인까지 완료했어."),
    ("중고 판매", "중고 거래 당근 시세 조사하고 판매글 등록 완료했어."),
    ("보험 청구", "실비 보험 청구 서류 제출 완료, 지급 확정 문자 확인했어."),
]

FORWARD_TASKS = [
    ("장보기 좀 부탁해", "이번 주 생필품 장보기 목록이야. 생수랑 기저귀 주문 부탁해."),
    ("식당 예약 요청", "다음 주 금요일 저녁 4명 식당 예약 해줘."),
    ("환불이 안 들어와요", "2주 전에 취소했는데 환불이 안 들어와. 환불 요구 좀 해줘."),
    ("구독 정리하고 싶어", "안 쓰는 구독 해지하고 미사용분 환불 되는지 알아봐줘."),
    ("가정통신문 처리", "학교에서 온 가정통신문인데 요약해서 알려줘."),
]

UNMATCHED_REPORTS = [
    ("어항 물갈이", "어항 물갈이랑 수초 정리 완료했어."),
    ("화분 분갈이", "베란다 화분 분갈이 끝냈어."),
    ("사진 백업", "오래된 사진 외장하드 백업 마쳤어."),
    ("기타 줄 교체", "기타 줄 교체하고 튜닝까지 완료."),
    ("자전거 체인 정비", "자전거 체인 정비 끝냈어."),
]


def mail_text(frm: str, to: str, subject: str, body: str) -> str:
    return f"---\nfrom: {frm}\nto: {to}\nsubject: {subject}\n---\n\n{body}\n"


def main() -> None:
    for d in (EMAILS, CUSTOMERS):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    profiles = {}
    for cid, name, region, factor in PEOPLE:
        prof = {
            "id": cid, "name": name,
            "address": f"{cid}.d3m0@unplugin.me",
            "contact": f"{cid}@example.com",
            "type": "SFRA", "tier": "one", "approval_limit": 30000,
            "deny_list": [], "onboarded": True,
            "region": region, "time_factor": factor,
            "movement_threshold_minutes": 180,
            "trusted_senders": [addr for _, addr in AGENTS],
        }
        (CUSTOMERS / cid).mkdir(parents=True)
        (CUSTOMERS / cid / "profile.json").write_text(
            json.dumps(prof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        profiles[cid] = prof

    emails, seq = [], 0

    def emit(kind: str, cid: str, agent: str, frm: str, subject: str, body: str,
             title: str) -> None:
        nonlocal seq
        seq += 1
        fname = f"{seq:03d}-{kind}-{cid}.md"
        (EMAILS / fname).write_text(
            mail_text(frm, profiles[cid]["address"], subject, body), encoding="utf-8")
        emails.append({"seq": seq, "file": f"emails/{fname}", "kind": kind,
                       "customer": cid, "agent": agent, "title": title})

    # [보고] 완료 메일 60통 — 고객 5 × 12 유형, 에이전트 순환 (결정적)
    for pi, (cid, name, region, factor) in enumerate(PEOPLE):
        for ti, (title, body) in enumerate(REPORT_TASKS):
            agent, addr = AGENTS[(pi + ti) % len(AGENTS)]
            emit("report", cid, agent, addr,
                 f"[보고] {title} 완료", f"{body}\n\n— {agent}", title)

    # 포워딩(팁 회신 유도) 20통 — 고객 5 × 4 유형
    for pi, (cid, name, region, factor) in enumerate(PEOPLE):
        for ti in range(4):
            title, body = FORWARD_TASKS[(pi + ti) % len(FORWARD_TASKS)]
            emit("forward", cid, "", profiles[cid]["contact"], title,
                 f"{body}", title)

    # 미매칭 보고 5통 — 고객당 1통 (기본값 적립 → Admin 백로그 시연)
    for pi, (cid, name, region, factor) in enumerate(PEOPLE):
        title, body = UNMATCHED_REPORTS[pi]
        agent, addr = AGENTS[pi % len(AGENTS)]
        emit("unmatched", cid, agent, addr, f"[보고] {title} 완료",
             f"{body}\n\n— {agent}", title)

    journeys = [{"n": i + 1, "customer": cid, "name": name, "region": region,
                 "time_factor": factor,
                 "title": f"{name}의 시간 배당 여정 ({region})",
                 "situation": "포워딩→팁 카드, 보고→적립, 임계치→무브먼트, 커뮤니티·Admin"}
                for i, (cid, name, region, factor) in enumerate(PEOPLE)]

    (DEMO_DIR / "index.json").write_text(json.dumps(
        {"version": "pivot-2026-11-04", "journeys": journeys, "emails": emails},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"고객 {len(PEOPLE)}명 · 메일 {len(emails)}통 "
          f"(보고 60 / 포워딩 20 / 미매칭 5) · 여정 {len(journeys)}건 생성")


if __name__ == "__main__":
    main()
