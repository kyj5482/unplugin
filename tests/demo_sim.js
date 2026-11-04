// demo.html 헤드리스 시뮬레이터 — 가상 시계 + 엄격 AudioParam (브라우저 예외 모사)
// 사용: node tests/demo_sim.js docs/demo.html
// 검증: 8장면이 전부 마디 경계에서 전환되고(프리즈 없음), 수동 점프/일시정지·재개/
// 다시 보기에서 에러 0이어야 한다. 2026-11-04 자동 적립 진입 프리즈(부동소수 경계
// 오차) 회귀 방지용 — 사운드 ON(재방문 기억) 경로 포함.
const fs = require("fs");
const html = fs.readFileSync(process.argv[2] || "docs/demo.html", "utf8");
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

// ── 가상 시계·타이머 ──
let VNOW = 0;
const Q = []; let qid = 1;
function addT(fn, ms, iv) { const t = { id: qid++, at: VNOW + Math.max(0, ms || 0), fn, iv: iv ? Math.max(1, ms) : 0 }; Q.push(t); return t.id; }
const errors = [];
function runUntil(target) {
  while (true) {
    Q.sort((a, b) => a.at - b.at);
    const t = Q.find(x => x.at <= target);
    if (!t) break;
    VNOW = t.at;
    if (t.iv) t.at = VNOW + t.iv; else Q.splice(Q.indexOf(t), 1);
    try { t.fn(); } catch (e) { errors.push({ t: VNOW, msg: e.message, stack: (e.stack||"").split("\n").slice(0,4).join(" | ") }); }
  }
  VNOW = target;
}

// ── DOM 스텁 ──
const log = [];
function mkEl(id) {
  const el = {
    id, _cls: new Set(), style: {}, dataset: {}, children: [], textContent: "", innerHTML: "",
    classList: {
      add: c => { if (id.startsWith("scene") && c === "on" && !el._cls.has("on")) log.push([VNOW, id + " ON"]); el._cls.add(c); },
      remove: c => el._cls.delete(c), toggle: (c, f) => { (f === undefined ? !el._cls.has(c) : f) ? el._cls.add(c) : el._cls.delete(c); },
      contains: c => el._cls.has(c),
    },
    setAttribute() {}, getAttribute() { return null; }, hasAttribute() { return false; },
    appendChild(c) { el.children.push(c); return c; }, querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {}, closest() { return null; },
    getBoundingClientRect() { return { left: 0, width: 100 }; }, setPointerCapture() {},
  };
  el.style.setProperty = () => {};
  Object.defineProperty(el, "offsetWidth", { get: () => 100 });
  return el;
}
const reg = new Map();
const byId = id => { if (!reg.has(id)) reg.set(id, mkEl(id)); return reg.get(id); };
const scenes = Array.from({ length: 8 }, (_, i) => byId("scene" + i));
const winHandlers = {};
const G = {
  console, Math, JSON, Number, Array, Object, String, Float32Array, Set, Map, Promise, Date, isFinite, parseFloat, parseInt,
  setTimeout: (f, ms) => addT(f, ms, false), clearTimeout: id => { const i = Q.findIndex(t => t.id === id); if (i >= 0) Q.splice(i, 1); },
  setInterval: (f, ms) => addT(f, ms, true), clearInterval: id => { const i = Q.findIndex(t => t.id === id); if (i >= 0) Q.splice(i, 1); },
  requestAnimationFrame: f => addT(() => f(VNOW), 16.7, false),
  performance: { now: () => VNOW },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  localStorage: { getItem: k => (k === "unplugin-demo-snd" ? "1" : "x"), setItem() {} },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  addEventListener: (ev, fn) => { (winHandlers[ev] = winHandlers[ev] || []).push(fn); },
  removeEventListener: (ev, fn) => { const a = winHandlers[ev] || []; const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1); },
  fetch: () => Promise.resolve({}), URL, location: { href: "x", origin: "o" },
  document: {
    querySelectorAll: sel => (sel === ".scene" ? scenes : []),
    getElementById: byId,
    addEventListener() {}, documentElement: byId("docEl"), body: byId("body"),
    createElement: () => mkEl("dyn" + qid),
  },
};

// ── 엄격 AudioParam — 브라우저와 동일하게 non-finite/비양수에서 throw ──
function param(name, v0) {
  const chk = (v, m) => { if (!Number.isFinite(v)) throw new TypeError(`${name}.${m}: non-finite value ${v}`); };
  return {
    _v: v0,
    get value() { return this._v; }, set value(v) { chk(v, "value="); this._v = v; },
    setValueAtTime(v, t) { chk(v, "setValueAtTime"); chk(t, "setValueAtTime(t)"); if (t < 0) throw new RangeError(name + " t<0"); },
    linearRampToValueAtTime(v, t) { chk(v, "linearRamp"); chk(t, "linearRamp(t)"); },
    exponentialRampToValueAtTime(v, t) { chk(v, "expRamp"); chk(t, "expRamp(t)"); if (v <= 0) throw new RangeError(name + " expRamp v<=0"); },
    setTargetAtTime(v, t, tc) { chk(v, "setTarget"); chk(t, "setTarget(t)"); chk(tc, "setTarget(tc)"); if (tc < 0) throw new RangeError(name + " tc<0"); },
    cancelScheduledValues(t) { chk(t, "cancel"); },
  };
}
function node(kind) {
  const n = { kind, connect(x) { return x; }, disconnect() {} };
  if (kind === "gain") n.gain = param("gain", 1);
  if (kind === "osc") { n.frequency = param("freq", 440); n.type = "sine"; n._st = 0;
    n.start = t => { if (n._st++) throw new Error("osc start twice"); if (t < 0) throw new RangeError("start t<0"); };
    n.stop = t => { if (!n._st) throw new Error("osc stop before start"); if (t < 0) throw new RangeError("stop t<0"); }; }
  if (kind === "biquad") { n.frequency = param("bq.freq", 350); n.Q = param("Q", 1); n.type = "lowpass"; }
  if (kind === "delay") n.delayTime = param("delayTime", 0);
  if (kind === "comp") { ["threshold","knee","ratio","attack","release"].forEach(k => n[k] = param(k, 0)); }
  if (kind === "shaper") { n.curve = null; n.oversample = "none"; }
  if (kind === "src") { n.buffer = null; n.loop = false; n._st = 0;
    n.start = t => { if (n._st++) throw new Error("src start twice"); if (t < 0) throw new RangeError("start t<0"); };
    n.stop = t => { if (!n._st) throw new Error("src stop before start"); if (t < 0) throw new RangeError("stop t<0"); }; }
  return n;
}
class FakeAC {
  constructor() { this.state = "running"; this.sampleRate = 44100; this.destination = node("dest"); }
  get currentTime() { return VNOW / 1000; }
  resume() { this.state = "running"; return Promise.resolve(); }
  suspend() { this.state = "suspended"; return Promise.resolve(); }
  createGain() { return node("gain"); } createOscillator() { return node("osc"); }
  createBiquadFilter() { return node("biquad"); } createDelay() { return node("delay"); }
  createDynamicsCompressor() { return node("comp"); } createWaveShaper() { return node("shaper"); }
  createBufferSource() { return node("src"); }
  createBuffer(ch, len, sr) { return { getChannelData: () => new Float32Array(Math.min(len, 1000)) }; }
}
G.window = { AudioContext: FakeAC };
G.AudioContext = FakeAC;
G.globalThis = G;

// ── 실행 ──
const vm = require("vm");
const ctx = vm.createContext(G);
for (const [i, b] of blocks.entries()) {
  try { vm.runInContext(b, ctx, { filename: "block" + i }); }
  catch (e) { errors.push({ t: VNOW, msg: "LOAD block" + i + ": " + e.message, stack: (e.stack||"").split("\n").slice(0,4).join(" | ") }); }
}
// 1초 시점: 사용자 제스처(재방문·소리 켬 기억) → unlock
runUntil(1000);
(winHandlers["pointerdown"] || []).slice().forEach(fn => { try { fn({ target: { closest: () => null } }); } catch (e) { errors.push({ t: VNOW, msg: "gesture: " + e.message }); } });
runUntil(20000);
// 수동 점프: 무브먼트(5) → 뒤로 적립(3)
try { byId("names").children[5].onclick(); } catch(e){ errors.push({t:VNOW,msg:"jump5: "+e.message}); }
runUntil(21000);
try { byId("names").children[3].onclick(); } catch(e){ errors.push({t:VNOW,msg:"jump3: "+e.message}); }
runUntil(23000);
// 일시정지 → 재개
try { byId("ppBtn").onclick(); } catch(e){ errors.push({t:VNOW,msg:"pause: "+e.message}); }
runUntil(25000);
try { byId("ppBtn").onclick(); } catch(e){ errors.push({t:VNOW,msg:"resume: "+e.message}); }
runUntil(120000);
// 끝난 뒤 다시 보기
try { byId("ppBtn").onclick(); } catch(e){ errors.push({t:VNOW,msg:"replay: "+e.message}); }
runUntil(200000);

console.log("── scene activations ──");
log.forEach(([t, s]) => console.log(String(Math.round(t)).padStart(6), s));
console.log("── errors:", errors.length, "──");
errors.slice(0, 10).forEach(e => console.log(Math.round(e.t), e.msg, "\n   ", e.stack || ""));
