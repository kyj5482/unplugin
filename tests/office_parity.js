// office_parity.js — 백오피스 JS 엔진 ↔ core(파이썬) 측정 의미론 패리티 검증.
// 사용: node tests/office_parity.js   (리포 루트 기준 상대 경로)
//
// ① python3 로 기대값 생성: 격리 UNPLUGIN_DATA 에 데모 고객 5명을 올리고
//    데모 메일 85통을 실제 core 함수(customer_by_address → is_report →
//    dividend.accrue / tips.make_tip)로 라우팅한 고객별 합계를 JSON 덤프.
// ② docs/office.html 의 [OFFICE-PURE] 엔진 + docs/office-data.js 로 같은
//    85통을 처리 → 고객별 {saved, emotion, events, matched, unmatched,
//    suggested, tips, quarantined} 가 완전 일치해야 PASS.
// ③ 추가: 스트레스 가중(환불 120/보증금 150), pyRound(뱅커스), 임계치 중복
//    방지, 팁 프롬프트 스냅샷 2건(문자열 완전 일치).
"use strict";
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}${detail ? " — " + detail : ""}`); }
}

/* ── ① 파이썬 기대값 ── */
const PY = `
import json, os, shutil, sys, tempfile
tmp = tempfile.mkdtemp(prefix="office-parity-")
os.environ["UNPLUGIN_DATA"] = os.path.join(tmp, "data")
os.environ["UNPLUGIN_FLOWS"] = os.path.join(tmp, "flows")
sys.path.insert(0, ${JSON.stringify(ROOT)})
from core import common, dividend, tips
from core.export_office import _demo_customers, _demo_mails
common.ensure_dirs()
profiles = {}
for p in _demo_customers():
    profiles[p["id"]] = p
    common.write_json(common.CUSTOMERS / p["id"] / "profile.json", p)

def route(mail):
    customer = common.customer_by_address(mail["to"])
    if customer is None:
        return ("bounce", None)
    sender = mail["from"].strip().lower()
    is_owner = sender == customer.get("contact", "").strip().lower()
    is_trusted = sender in [s.strip().lower() for s in customer.get("trusted_senders", [])]
    if not (is_owner or is_trusted):
        return ("quarantined", customer["id"])
    if dividend.is_report(mail):
        r = dividend.accrue(customer["id"], mail)
        return ("report", (customer["id"], r))
    if is_owner:
        card = tips.make_tip(f"{mail.get('subject','')} {mail.get('body','')}", customer)
        return ("tip", (customer["id"], card))
    return ("archived", customer["id"])

stats = {cid: {"saved": 0, "emotion": 0, "events": 0, "matched": 0,
               "unmatched": 0, "suggested": 0, "tips": 0, "quarantined": 0}
         for cid in profiles}
for mail in _demo_mails():
    kind, info = route(mail)
    if kind == "report":
        cid, r = info
        s = stats[cid]
        s["events"] += 1
        s["saved"] = r["total_saved_minutes"]
        s["emotion"] += r["emotion_load"]
        s["matched" if r["matched"] else "unmatched"] += 1
        if r["suggested"]:
            s["suggested"] += 1
    elif kind == "tip":
        stats[info[0]]["tips"] += 1
    elif kind == "quarantined":
        stats[info]["quarantined"] += 1

jisoo = profiles["jisoo"]
out = {
    "stats": stats,
    "tip_snap_stress": tips.make_tip("결항된 제주 항공권 환불 받아줘", jisoo)["muze_prompt"],
    "tip_snap_plain": tips.make_tip("이번 주 생필품 주문", None)["muze_prompt"],
    "match_refund": dividend._match_task("쇼핑몰 환불이 두 달째 안 들어와요"),
    "match_deposit": dividend._match_task("이사한 집 보증금을 안 돌려줘요"),
    "pyround": [round(x) for x in (22.5, 37.5, 67.5, 45 * 1.5, 40 * 1.3, 75 * 0.8, 1.5, 2.5)],
}
print(json.dumps(out, ensure_ascii=False))
shutil.rmtree(tmp, ignore_errors=True)
`;
const py = spawnSync("python3", ["-"], { input: PY, cwd: ROOT, encoding: "utf-8" });
if (py.status !== 0) {
  console.error("python3 기대값 생성 실패:\n" + py.stderr);
  process.exit(1);
}
const EXP = JSON.parse(py.stdout.trim().split("\n").pop());

/* ── ② JS 엔진 로드 (OFFICE-PURE 블록) ── */
const DATA = require(path.join(ROOT, "docs", "office-data.js"));
const html = fs.readFileSync(path.join(ROOT, "docs", "office.html"), "utf-8");
const m = html.match(/\[OFFICE-PURE-BEGIN\][\s\S]*?═+ \*\/\n([\s\S]*?)\/\* ═+ \[OFFICE-PURE-END\]/);
if (!m) { console.error("OFFICE-PURE 블록을 찾지 못함"); process.exit(1); }
function loadEngine(code) {
  const module = { exports: {} };   // 블록 끝의 module.exports 가 테스트 모듈을 오염하지 않게 격리
  eval(code);
  return module.exports;
}
const OFFICE = loadEngine(m[1]);

/* ── JS 쪽 동일 파이프라인 ── */
const state = { customers: {}, ledgers: {}, community: { groups: {} } };
for (const p of DATA.demo_customers) state.customers[p.id] = JSON.parse(JSON.stringify(p));
const got = {};
for (const cid of Object.keys(state.customers))
  got[cid] = { saved: 0, emotion: 0, events: 0, matched: 0, unmatched: 0,
               suggested: 0, tips: 0, quarantined: 0 };
for (const mail of DATA.demo_mails) {
  const r = OFFICE.routeMail(state, mail, DATA, "2026-11-05T00:00:00");
  if (r.action === "report_accrued") {
    const s = got[r.customer], rr = r.result;
    s.events += 1; s.saved = rr.total_saved_minutes; s.emotion += rr.emotion_load;
    s[rr.matched ? "matched" : "unmatched"] += 1;
    if (rr.suggested) s.suggested += 1;
  } else if (r.action === "tip_sent") got[r.customer].tips += 1;
  else if (r.action === "quarantined") got[r.customer].quarantined += 1;
}

/* ── ③ 비교 ── */
console.log("고객별 합계 (JS ↔ Python):");
for (const cid of Object.keys(EXP.stats).sort()) {
  const e = EXP.stats[cid], g = got[cid];
  const same = JSON.stringify(e) === JSON.stringify(g);
  console.log(`  ${cid.padEnd(6)} saved ${String(g.saved).padStart(4)}/${String(e.saved).padStart(4)}` +
    ` 감정 ${g.emotion}/${e.emotion} 적립 ${g.events}/${e.events}` +
    ` 매칭 ${g.matched}/${e.matched} 미매칭 ${g.unmatched}/${e.unmatched}` +
    ` 제안 ${g.suggested}/${e.suggested} 팁 ${g.tips}/${e.tips}  ${same ? "✓" : "✗"}`);
  check(`parity:${cid}`, same, same ? "" : JSON.stringify({ js: g, py: e }));
}

const mr = OFFICE.matchTask("쇼핑몰 환불이 두 달째 안 들어와요", DATA);
check("stress:환불 120분·감정5", mr.saved_minutes === EXP.match_refund.saved_minutes
  && mr.emotion_load === EXP.match_refund.emotion_load
  && mr.saved_minutes === 120 && mr.emotion_load === 5,
  JSON.stringify({ js: mr, py: EXP.match_refund }));
const md = OFFICE.matchTask("이사한 집 보증금을 안 돌려줘요", DATA);
check("stress:보증금 150분·감정5", md.saved_minutes === EXP.match_deposit.saved_minutes
  && md.emotion_load === EXP.match_deposit.emotion_load && md.saved_minutes === 150,
  JSON.stringify({ js: md, py: EXP.match_deposit }));

const jsRound = [22.5, 37.5, 67.5, 45 * 1.5, 40 * 1.3, 75 * 0.8, 1.5, 2.5].map(OFFICE.pyRound);
check("pyRound 뱅커스 라운딩", JSON.stringify(jsRound) === JSON.stringify(EXP.pyround),
  `js=${JSON.stringify(jsRound)} py=${JSON.stringify(EXP.pyround)}`);

const jisoo = state.customers["jisoo"];
const snapS = OFFICE.makeTip("결항된 제주 항공권 환불 받아줘", jisoo, DATA).muze_prompt;
check("팁 스냅샷(스트레스) 문자열 일치", snapS === EXP.tip_snap_stress,
  snapS === EXP.tip_snap_stress ? "" : `\nJS: ${snapS}\nPY: ${EXP.tip_snap_stress}`);
const snapP = OFFICE.makeTip("이번 주 생필품 주문", null, DATA).muze_prompt;
check("팁 스냅샷(일반·플레이스홀더) 문자열 일치", snapP === EXP.tip_snap_plain,
  snapP === EXP.tip_snap_plain ? "" : `\nJS: ${snapP}\nPY: ${EXP.tip_snap_plain}`);

// 임계치 중복 방지 — 같은 구간 추가 적립에 재제안 없음
{
  const st = { customers: { t: { id: "t", name: "테", time_factor: 1.0,
    movement_threshold_minutes: 180, contact: "t@x.com", address: "t.aaaa@unplugin.me",
    trusted_senders: ["a@x.com"] } }, ledgers: {}, community: { groups: {} } };
  const mk = s => ({ from: "a@x.com", to: "t.aaaa@unplugin.me", subject: "[보고] " + s,
                     body: "처리했어" });
  // 90분짜리(구독 해지 환불) 2건 → 180 도달 제안 1회, 3건째(270)는 같은 구간 아님(1→1) 확인
  const r1 = OFFICE.routeMail(st, mk("구독 해지 환불 완료"), DATA, "2026-11-05T00:00:00").result;
  const r2 = OFFICE.routeMail(st, mk("구독 해지 환불 완료 2"), DATA, "2026-11-05T00:00:01").result;
  const r3 = OFFICE.routeMail(st, mk("구독 해지 환불 완료 3"), DATA, "2026-11-05T00:00:02").result;
  check("임계치: 180 도달 시 1회 제안·중복 없음",
    r1.suggested === false && r2.suggested === true && r3.suggested === false,
    JSON.stringify([r1.suggested, r2.suggested, r3.suggested]));
}

// 데이터 지속성 — localStorage 모킹: 직렬화 왕복 후에도 상태·임계치 연속성이 유지
{
  const store = {};   // localStorage 모킹
  const mockLS = { setItem: (k, v) => { store[k] = String(v); },
                   getItem: k => (k in store ? store[k] : null) };
  const st = { customers: { t: { id: "t", name: "테", time_factor: 1.2,
    movement_threshold_minutes: 180, contact: "t@x.com", address: "t.aaaa@unplugin.me",
    trusted_senders: [] } }, ledgers: {}, community: { groups: {} } };
  const mk = s => ({ from: "t@x.com", to: "t.aaaa@unplugin.me", subject: "[보고] " + s,
                     body: "처리했어" });
  OFFICE.routeMail(st, mk("구독 해지 환불"), DATA, "2026-11-05T00:00:00");
  mockLS.setItem("unplugin-office-v1", JSON.stringify(st));          // 저장
  const st2 = JSON.parse(mockLS.getItem("unplugin-office-v1"));     // 새 세션 복원
  const before = st2.ledgers.t.totals.saved_minutes;
  const r2 = OFFICE.routeMail(st2, mk("구독 해지 환불 2"), DATA, "2026-11-05T00:00:01").result;
  check("지속성: localStorage 왕복 후 잔고·임계치 연속",
    before === 108 && r2.total_saved_minutes === 216 && r2.suggested === true,
    JSON.stringify({ before, after: r2.total_saved_minutes, suggested: r2.suggested }));
  check("지속성: office.html 이 localStorage 키를 사용",
    html.includes('localStorage.setItem(KEY') || html.includes("localStorage.setItem(KEY"),
    "setItem(KEY) 미발견");
}

// 수신 분기 — 미발급 주소 bounce / 미등록 발신 격리 (TC-OFC-002)
{
  const st = { customers: { t: { id: "t", name: "테", contact: "t@x.com",
    address: "t.aaaa@unplugin.me", trusted_senders: ["muze@a.com"] } },
    ledgers: {}, community: { groups: {} } };
  const b = OFFICE.routeMail(st, { from: "a@b.c", to: "nobody@unplugin.me",
    subject: "[보고] x", body: "" }, DATA);
  const q = OFFICE.routeMail(st, { from: "stranger@evil.com", to: "t.aaaa@unplugin.me",
    subject: "[보고] 대박 환급", body: "완료" }, DATA);
  check("수신: 미발급 주소 bounce · 미등록 발신 격리",
    b.action === "bounce" && q.action === "quarantined",
    JSON.stringify([b.action, q.action]));
}

// 온보딩·보정 — 주소 발급 형식과 계수 클램프 (TC-OFC-003)
{
  const id = OFFICE.slugId("김 지수!");
  const addr = OFFICE.newAddress(id, "k7x2");
  check("온보딩: slug·전용주소 형식",
    id === "김-지수" && addr === "김-지수.k7x2@unplugin.me", `${id} / ${addr}`);
  check("보정: clampFactor 0.5~2.0",
    OFFICE.clampFactor(3) === 2.0 && OFFICE.clampFactor(0.1) === 0.5
    && OFFICE.clampFactor("abc") === 1.0 && OFFICE.clampFactor(1.3) === 1.3, "");
}

// 커뮤니티 — 같은 그룹+지역 모임 섹션과 다이제스트 주기 중복 방지 (TC-OFC-004)
{
  const meets = Object.keys(state.customers)
    .map(cid => OFFICE.meetupSection(state, cid, DATA)).filter(Boolean);
  check("커뮤니티: 같은 그룹+지역 ≥2 모임 섹션 생성", meets.length >= 2,
    `섹션 ${meets.length}건`);
  const now = Date.now();
  const first = OFFICE.communityTick(state, DATA, now, true);
  const sent1 = first.filter(r => r.sent).length;
  const second = OFFICE.communityTick(state, DATA, now + 1000, false);
  const sent2 = second.filter(r => r.sent).length;
  const skipped = second.filter(r => r.detail === "주기 미도래").length;
  check("커뮤니티: 다이제스트 주기(7일) 중복 방지",
    sent1 > 0 && sent2 === 0 && skipped > 0,
    JSON.stringify({ sent1, sent2, skipped }));
}

console.log(`\n결과: ${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
