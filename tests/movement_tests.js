// movement_tests.js — 무브먼트 실험 10종 순수 로직 검증 (node tests/movement_tests.js)
// docs/office.html 의 [OFFICE-PURE]·[MOVEMENT-PURE] 블록을 로드해 데모 데이터로 검증.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DATA = require(path.join(ROOT, "docs", "office-data.js"));
const html = fs.readFileSync(path.join(ROOT, "docs", "office.html"), "utf-8");

function block(name) {
  const m = html.match(new RegExp(`\\[${name}-BEGIN\\][\\s\\S]*?═+ \\*\\/\\n([\\s\\S]*?)\\/\\* ═+ \\[${name}-END\\]`));
  if (!m) { console.error(`${name} 블록 없음`); process.exit(1); }
  return m[1];
}
function loadEngines() {
  const module = { exports: {} };   // 블록 끝 module.exports 주입을 받아낸다
  eval(block("OFFICE-PURE") + "\n" + block("MOVEMENT-PURE"));
  return { OFFICE: module.exports, MOVEMENT: module.exports.MOVEMENT };
}
const { OFFICE, MOVEMENT } = loadEngines();

let pass = 0, fail = 0;
const check = (name, ok, detail) => {
  if (ok) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (detail ? " — " + detail : "")); }
};

// ── 데모 상태 구성: 85통 처리로 잔고·그룹 형성 ──
const S = { customers: {}, ledgers: {}, community: { groups: {} },
            movement: MOVEMENT.emptyMovement() };
for (const p of DATA.demo_customers) S.customers[p.id] = JSON.parse(JSON.stringify(p));
for (const mail of DATA.demo_mails) OFFICE.routeMail(S, mail, DATA, "2026-11-05T00:00:00");
const M = S.movement;
const NOW = Date.parse("2026-11-05T09:00:00");
const groups = OFFICE.memberships(S, DATA);

// 1~2) ICS — RFC5545 필수 필드 + CRLF + 주말 슬롯
{
  const slot = MOVEMENT.nextWeekendSlot(NOW, 60);
  check("ICS: 주말 슬롯은 미래의 토요일",
    slot.start > NOW && new Date(slot.start).getDay() === 6
    && slot.end - slot.start === 60 * 60000,
    new Date(slot.start).toString());
  const ics = MOVEMENT.icsFile({ uid: "u1@unplugin.me", start: slot.start, end: slot.end,
    summary: "되찾은 시간 — 산책", description: "테스트", nowMs: NOW });
  const must = ["BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:u1@unplugin.me",
    "DTSTAMP:", "DTSTART:", "DTEND:", "SUMMARY:되찾은 시간 — 산책", "END:VEVENT", "END:VCALENDAR"];
  check("ICS: RFC5545 필수 필드 + CRLF",
    must.every(f => ics.includes(f)) && ics.split("\r\n").length > 10 && !/[^\r]\n/.test(ics),
    ics.slice(0, 120));
}

// 3~4) time-lock — 차감·기록·잔고 부족
{
  const before = MOVEMENT.balanceOf(S, "jisoo");
  const r = MOVEMENT.timeLock(S, M, "jisoo", 60, "배움 — 원데이 클래스", NOW);
  check("time-lock: 차감 + ledger.movements 기록 + 스탬프",
    r.ok && MOVEMENT.balanceOf(S, "jisoo") === before - 60
    && S.ledgers.jisoo.movements.length === 1
    && S.ledgers.jisoo.movements[0].source === "time-lock"
    && (M.stamps.jisoo || []).length === 1,
    JSON.stringify(r));
  const r2 = MOVEMENT.timeLock(S, M, "jisoo", 99999, "x", NOW);
  check("time-lock: 잔고 부족 거부(차감 없음)",
    !r2.ok && MOVEMENT.balanceOf(S, "jisoo") === before - 60, JSON.stringify(r2));
}

// 5~7) lightning — 매칭 정합·중복 방지·RSVP 성사
{
  const created = MOVEMENT.lightningPropose(S, M, DATA, groups, NOW);
  const regionsOk = created.every(p => {
    const regs = new Set(p.members.map(c => S.customers[c].region));
    return regs.size === 1 && p.members.length >= 2 && [...regs][0] === p.region;
  });
  check("lightning: 같은 그룹+같은 지역 ≥2 만 매칭", created.length >= 1 && regionsOk,
    JSON.stringify(created.map(p => p.key)));
  const again = MOVEMENT.lightningPropose(S, M, DATA, groups, NOW);
  check("lightning: 활성 제안 중복 생성 방지", again.length === 0, `재생성 ${again.length}건`);
  const p = created[0];
  MOVEMENT.lightningRsvp(M, p.key, p.members[0], true);
  check("lightning: 1명 수락으로는 미성사", p.status === "제안", p.status);
  MOVEMENT.lightningRsvp(M, p.key, p.members[1], true);
  const st = MOVEMENT.lightningStats(M);
  check("lightning: 2명 수락 → 성사 + 성사율 집계",
    p.status === "성사" && st.done === 1 && st.rate === Math.round(1 / st.proposed * 100),
    JSON.stringify(st));
  check("lightning: 장소 후보는 지역 코스에서", p.places.length > 0
    && (DATA.local_courses[p.region] || []).some(c => c.title === p.places[0]),
    JSON.stringify(p.places));
}

// 8~10) season — 클램프·정원/대기열·중복 신청·매출
{
  const s = MOVEMENT.seasonCreate(M, { name: "테스트 시즌", rounds: 12, price: 999999, capacity: 2 });
  check("season: 회차 4~8·가격 10~25만 클램프", s.rounds === 8 && s.price === 250000,
    JSON.stringify([s.rounds, s.price]));
  MOVEMENT.seasonApply(M, s.id, "jisoo");
  MOVEMENT.seasonApply(M, s.id, "minho");
  const w = MOVEMENT.seasonApply(M, s.id, "sora");
  check("season: 정원 초과 → 대기열", w.ok && w.status === "대기열"
    && s.applicants.length === 2 && s.waitlist.length === 1, JSON.stringify(s));
  const dup = MOVEMENT.seasonApply(M, s.id, "jisoo");
  check("season: 중복 신청 거부 + 매출 = 가격×확정",
    !dup.ok && MOVEMENT.seasonRevenue(s) === 500000,
    JSON.stringify([dup, MOVEMENT.seasonRevenue(s)]));
}

// 11) partner-voucher — 자격·수수료 집계
{
  const pt = MOVEMENT.partnerAdd(M, { name: "성수 가죽공방", region: "성수동", feePct: 30 });
  check("voucher: 수수료 15~20% 클램프", pt.feePct === 20, String(pt.feePct));
  const elig = MOVEMENT.voucherEligible(S);
  check("voucher: 자격 = 잔고(적립-전환) ≥ 임계치", elig.length >= 1
    && elig.every(c => MOVEMENT.balanceOf(S, c) >= 180), JSON.stringify(elig));
  const v = MOVEMENT.voucherIssue(M, elig[0], pt.id, NOW);
  const dup = MOVEMENT.voucherIssue(M, elig[0], pt.id, NOW);
  const u = MOVEMENT.voucherUse(M, v.voucher.id, 80000, NOW);
  check("voucher: 발급→중복 방지→사용 수수료 20%·누계",
    v.ok && !dup.ok && u.ok && u.fee === 16000 && M.feeTotal === 16000,
    JSON.stringify([v.ok, dup, u]));
}

// 12) timebank — 매칭·재매칭 방지·본인 매칭 방지
{
  const o = MOVEMENT.timebankPost(M, { cid: "jisoo", kind: "offer", text: "환불 노하우 1:1" });
  const r = MOVEMENT.timebankPost(M, { cid: "minho", kind: "request", text: "베이킹 기초" });
  const self = MOVEMENT.timebankPost(M, { cid: "jisoo", kind: "request", text: "셀프" });
  const bad = MOVEMENT.timebankMatch(M, o.item.id, self.item.id, NOW);
  const m1 = MOVEMENT.timebankMatch(M, o.item.id, r.item.id, NOW);
  const m2 = MOVEMENT.timebankMatch(M, o.item.id, r.item.id, NOW);
  check("timebank: 본인 매칭 거부·성사 양쪽 기록·재매칭 방지",
    !bad.ok && m1.ok && m1.match.between.join() === "jisoo,minho" && !m2.ok
    && (M.stamps.minho || []).some(s => s.source === "timebank"),
    JSON.stringify([bad, m1.ok, m2]));
}

// 13) buddy — 그룹 내 2인·자기쌍 없음·양쪽 확인 완료
{
  const created = MOVEMENT.buddyPair(M, groups);
  const okShape = created.every(b => b.a !== b.b
    && groups[b.group].some(m => m.customer === b.a)
    && groups[b.group].some(m => m.customer === b.b));
  check("buddy: 같은 그룹 2인 짝·자기쌍 없음", created.length >= 1 && okShape,
    JSON.stringify(created.map(b => [b.group, b.a, b.b])));
  const b = created[0];
  MOVEMENT.buddyPromise(M, b.id, "토요일 시장 산책", "2026-11-08");
  MOVEMENT.buddyConfirm(M, b.id, b.a, NOW);
  check("buddy: 한쪽 확인만으로는 미완료", !b.done, JSON.stringify(b.confirms));
  MOVEMENT.buddyConfirm(M, b.id, b.b, NOW);
  check("buddy: 양쪽 확인 → 완료 + 양쪽 스탬프", b.done
    && (M.stamps[b.a] || []).some(s => s.source === "buddy")
    && (M.stamps[b.b] || []).some(s => s.source === "buddy"), JSON.stringify(b));
  const again = MOVEMENT.buddyPair(M, groups);
  const rePaired = again.some(x => [x.a, x.b].some(c => MOVEMENT.buddyActive(M, c) &&
    M.buddies.filter(y => !y.done && (y.a === c || y.b === c)).length > 1));
  check("buddy: 활성 쌍 중복 매칭 방지", !rePaired, "");
}

// 14) challenge — 중복 인증 거부·연속 스트릭
{
  const c = MOVEMENT.challengeCreate(M, "토요일 아침 시장 산책", NOW);
  MOVEMENT.challengeJoin(M, c.id, "yuna");
  const d1 = MOVEMENT.challengeCheckin(M, c.id, "yuna", "2026-11-01");
  const dup = MOVEMENT.challengeCheckin(M, c.id, "yuna", "2026-11-01");
  MOVEMENT.challengeCheckin(M, c.id, "yuna", "2026-11-02");
  const d3 = MOVEMENT.challengeCheckin(M, c.id, "yuna", "2026-11-03");
  check("challenge: 같은 날 중복 인증 거부", d1.ok && !dup.ok, JSON.stringify(dup));
  check("challenge: 연속 3일 스트릭", d3.ok && d3.streak === 3, JSON.stringify(d3));
  check("challenge: 공백 후 스트릭 리셋",
    MOVEMENT.streakOf(["2026-11-01", "2026-11-03", "2026-11-04"]) === 2, "");
}

// 15) stamps — 레벨 경계
{
  check("stamps: 레벨 경계 (0/1/3/6/10)",
    MOVEMENT.levelOf(0) === "아직 스탬프 없음" && MOVEMENT.levelOf(1).includes("Lv1")
    && MOVEMENT.levelOf(3).includes("Lv2") && MOVEMENT.levelOf(6).includes("Lv3")
    && MOVEMENT.levelOf(10).includes("Lv4"), "");
}

// 16) local-course — region 매칭
{
  const { region, courses } = MOVEMENT.coursesFor(S, DATA, "jisoo");
  check("local-course: 고객 region 코스 매칭", region === "성수동" && courses.length === 3
    && courses.every(c => c.title && c.duration_min > 0), JSON.stringify(courses.map(c => c.id)));
}

// 17) gift-time — 차감 + 초대문안 + ICS
{
  const before = MOVEMENT.balanceOf(S, "doyun");
  const r = MOVEMENT.giftTime(S, M, "doyun", 90, "소연", NOW);
  check("gift-time: 차감·초대문안·ICS SUMMARY",
    r.ok && MOVEMENT.balanceOf(S, "doyun") === before - 90
    && r.invite.includes("소연님께") && r.ics.includes("SUMMARY:")
    && r.ics.includes("선물한 시간"), JSON.stringify({ before, after: MOVEMENT.balanceOf(S, "doyun") }));
}

// 18) movement 상태 직렬화 왕복 (localStorage 스키마 통합)
{
  const copy = MOVEMENT.migrate(JSON.parse(JSON.stringify(M)));
  check("직렬화: movement 네임스페이스 왕복 무손실",
    copy.locks.length === M.locks.length && copy.feeTotal === M.feeTotal
    && copy.seasons.length === M.seasons.length
    && Object.keys(copy.stamps).length === Object.keys(M.stamps).length, "");
}

console.log(`\n결과: ${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
