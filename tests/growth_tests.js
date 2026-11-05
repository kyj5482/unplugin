// growth_tests.js — 성장 추천 엔진([GROWTH-PURE]) 검증 (node tests/growth_tests.js)
// 타입(4축)별 추천 차이·잔고 문턱·반복 회피·점진 설계·문안·결정성.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DATA = require(path.join(ROOT, "docs", "office-data.js"));
const html = fs.readFileSync(path.join(ROOT, "docs", "office.html"), "utf-8");
const block = name => {
  const m = html.match(new RegExp(`\\[${name}-BEGIN\\][\\s\\S]*?═+ \\*\\/\\n([\\s\\S]*?)\\/\\* ═+ \\[${name}-END\\]`));
  if (!m) { console.error(`${name} 블록 없음`); process.exit(1); }
  return m[1];
};
function loadEngines() {
  const module = { exports: {} };
  eval(block("OFFICE-PURE") + "\n" + block("MOVEMENT-PURE") + "\n" + block("GROWTH-PURE"));
  return { OFFICE: module.exports, MOVEMENT: module.exports.MOVEMENT,
           GROWTH: module.exports.GROWTH };
}
const { OFFICE, MOVEMENT, GROWTH } = loadEngines();

let pass = 0, fail = 0;
const check = (name, ok, detail) => {
  if (ok) { pass++; console.log("PASS  " + name); }
  else { fail++; console.log("FAIL  " + name + (detail ? " — " + detail : "")); }
};
const deep = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// 데모 상태 — 85통 적립으로 잔고·그룹 형성
function freshState() {
  const S = { customers: {}, ledgers: {}, community: { groups: {} },
              movement: MOVEMENT.emptyMovement(), growth: GROWTH.emptyGrowth() };
  for (const p of DATA.demo_customers) S.customers[p.id] = JSON.parse(JSON.stringify(p));
  for (const mail of DATA.demo_mails) OFFICE.routeMail(S, mail, DATA, "2026-11-05T00:00:00");
  return S;
}
const S = freshState();
const groups = OFFICE.memberships(S, DATA);

// 1) 결정성 — 같은 입력이면 완전히 같은 출력
{
  const a = GROWTH.recommend(S, DATA, "jisoo", groups, 3);
  const b = GROWTH.recommend(S, DATA, "jisoo", groups, 3);
  check("결정성: 같은 입력 → 같은 출력", deep(a, b), "");
}

// 2~3) P/A 축 — 함께형은 관계, 혼자형은 솔로
{
  const j = GROWTH.recommend(S, DATA, "jisoo", groups, 3);   // SFRP 함께/오감
  const s = GROWTH.recommend(S, DATA, "sora", groups, 3);    // TCRA 혼자/오감
  check("P축(jisoo·함께): 3주차 primary = 관계", j.primary.kind === "관계",
    JSON.stringify(j.primary));
  check("A축(sora·혼자): 3주차 primary = 솔로", s.primary.mode !== "together"
    && s.primary.kind !== "관계", JSON.stringify(s.primary));
}

// 4) M/R 축 — 만들기형은 배움, 감각형은 오감
{
  const y = GROWTH.recommend(S, DATA, "yuna", groups, 1);    // SFMA 혼자/배움
  const d = GROWTH.recommend(S, DATA, "doyun", groups, 1);   // TFRA 혼자/오감
  check("M축(yuna): 배움(공방) 우선 / R축(doyun): 오감 우선",
    y.primary.kind === "배움" && d.primary.kind === "오감",
    JSON.stringify([y.primary.title, d.primary.title]));
}

// 5) 점진 설계 — 같은 함께형(jisoo)도 1주차는 솔로, 3주차에 관계로
{
  const w1 = GROWTH.recommend(S, DATA, "jisoo", groups, 1);
  const w3 = GROWTH.recommend(S, DATA, "jisoo", groups, 3);
  check("점진: jisoo 1주차 솔로 → 3주차 관계",
    w1.primary.mode === "solo" && w3.primary.kind === "관계",
    JSON.stringify([w1.primary.title, w3.primary.title]));
}

// 6~7) 잔고 문턱 — 작으면 30분 산책, 잔고 초과 후보는 아예 제외
{
  const T = { customers: { t: { id: "t", name: "테", type: "SFRP", region: "성수동",
    time_factor: 1, movement_threshold_minutes: 180, contact: "t@x.com",
    address: "t.x@unplugin.me", trusted_senders: [] } },
    ledgers: { t: { customer: "t", totals: { saved_minutes: 40, emotion_saved: 0,
      events_count: 1, spent_minutes: 0 }, last_suggested_at_minutes: 0, events: [] } },
    movement: MOVEMENT.emptyMovement(), growth: GROWTH.emptyGrowth() };
  const r = GROWTH.recommend(T, DATA, "t", {}, 3);
  check("잔고 문턱: 잔고 40분 → primary = 30분 산책", r.primary.id === "rest:walk30",
    JSON.stringify(r.primary));
  const all = [r.primary, ...r.alternatives];
  check("잔고 초과 후보 제외: 모든 제안 ≤ 잔고", all.every(c => c.minutes <= 40),
    JSON.stringify(all.map(c => [c.id, c.minutes])));
}

// 8) 반복 회피 — 직전 실행과 같은 활동은 다음 주 primary 에서 밀려난다
{
  const T = freshState();
  const first = GROWTH.recommend(T, DATA, "jisoo", groups, 3);
  T.growth.proposals.jisoo = [{ week: 3, t: "2026-11-05T00:00:00",
    primary: first.primary, alts: first.alternatives, mail: first.mail, status: "실행" }];
  const next = GROWTH.recommend(T, DATA, "jisoo", groups, 4);
  check("반복 회피: 직전 primary 와 다른 제안", next.primary.id !== first.primary.id,
    JSON.stringify([first.primary.id, next.primary.id]));
}

// 9) A형 관계 문턱 — 혼자형의 '함께' 후보 중에서는 1:1 짝꿍이 가장 앞
{
  const ax = GROWTH.axes(S.customers.doyun.type);   // TFRA — A
  const scored = GROWTH.candidates(S, DATA, "doyun", groups)
    .map(c => Object.assign({}, c, GROWTH.score(c, ax, MOVEMENT.balanceOf(S, "doyun"), 3, [])))
    .filter(c => c.s > -999 && c.mode === "together")
    .sort((a, b) => b.s - a.s);
  check("A형 점진: 함께 후보 1순위 = 짝꿍(1:1)", scored.length > 0 && !!scored[0].buddy,
    JSON.stringify(scored.map(c => [c.id, c.s])));
}

// 10) 대안 — 2개·중복 없음
{
  const r = GROWTH.recommend(S, DATA, "minho", groups, 2);
  const ids = [r.primary.id, ...r.alternatives.map(a => a.id)];
  check("대안: primary + 대안 2, id 중복 없음",
    r.alternatives.length === 2 && new Set(ids).size === 3, JSON.stringify(ids));
}

// 11) region 없는 고객 — 코스 없이도 추천 성립 (번개 후보 없음)
{
  const T = freshState();
  delete T.customers.doyun.region;
  const r = GROWTH.recommend(T, DATA, "doyun", OFFICE.memberships(T, DATA), 1);
  check("무지역: 기본 후보(30분 산책)로 성립·번개 없음",
    !!r.primary && ![r.primary, ...r.alternatives].some(c => c.mech === "lightning"),
    JSON.stringify(r.primary));
}

// 12) 문안 — 이름·주차·타입명·★제안·대안·회신 안내 포함 (+ 제목 고정)
{
  const r = GROWTH.recommend(S, DATA, "jisoo", groups, 3);
  const b = r.mail.body;
  const need = ["지수님, 3주차", "노을 피크닉러", "★ " + r.primary.title,
    ...r.alternatives.map(a => "- " + a.title), "회신으로 알려주세요"];
  check("문안: 필수 요소 전부 포함 + 제목 형식",
    need.every(t => b.includes(t)) && r.mail.subject === `이번 주 무브먼트 — ${r.primary.title}`,
    b.slice(0, 160));
}

// 13) weekOf/historyOf — 제안 기록이 주차·이력에 반영
{
  const T = freshState();
  check("weekOf: 제안 전 1주차", GROWTH.weekOf(T, "yuna") === 1, "");
  const r = GROWTH.recommend(T, DATA, "yuna", groups, 1);
  T.growth.proposals.yuna = [{ week: 1, t: "2026-11-05T00:00:00",
    primary: r.primary, alts: r.alternatives, mail: r.mail, status: "발송" }];
  check("weekOf/historyOf: 기록 후 2주차·이력 포함",
    GROWTH.weekOf(T, "yuna") === 2
    && GROWTH.historyOf(T, "yuna").some(h => h.id === r.primary.id), "");
}

// 14) 5고객 추천 표 — 전원 성립 + 타입별 차이 (primary 종류 ≥2)
{
  console.log("── 5고객 1주차/3주차 추천 표 ──");
  const kinds = new Set();
  let allOk = true;
  for (const cid of Object.keys(S.customers).sort()) {
    const w1 = GROWTH.recommend(S, DATA, cid, groups, 1);
    const w3 = GROWTH.recommend(S, DATA, cid, groups, 3);
    allOk = allOk && !!w1.primary && !!w3.primary;
    kinds.add(w1.primary.kind + "/" + w3.primary.kind);
    console.log(`  ${cid.padEnd(6)} ${(S.customers[cid].type || "").padEnd(5)}` +
      ` 1주차: ${w1.primary.title} (${w1.primary.kind})  |  3주차: ${w3.primary.title} (${w3.primary.kind})`);
  }
  check("5고객: 전원 추천 성립 + 타입별 차이", allOk && kinds.size >= 2,
    JSON.stringify([...kinds]));
}

console.log(`\n결과: ${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
