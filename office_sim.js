// office.html 탭 렌더 시뮬 — DOM 스텁으로 각 탭의 render() 예외를 재현
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname);
const html = fs.readFileSync(path.join(ROOT, "docs/office.html"), "utf8");
const dataJs = fs.readFileSync(path.join(ROOT, "docs/office-data.js"), "utf8");
const blocks = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

function mkEl() {
  const el = {
    _html: "", style: {}, dataset: {}, value: "", textContent: "",
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    setAttribute(){}, getAttribute(){ return null; }, appendChild(c){ return c; },
    addEventListener(){}, removeEventListener(){}, click(){}, focus(){},
    querySelector(){ return mkEl(); }, querySelectorAll(){ return []; },
    getBoundingClientRect(){ return { left:0, width:100 }; },
  };
  Object.defineProperty(el, "innerHTML", { get(){ return el._html; }, set(v){ el._html = String(v); } });
  return el;
}
function runTab(hash) {
  const reg = new Map();
  const byId = id => { if (!reg.has(id)) reg.set(id, mkEl()); return reg.get(id); };
  const G = {
    console, Math, JSON, Date, Number, String, Array, Object, Set, Map, parseInt, parseFloat, isFinite, encodeURIComponent, decodeURIComponent,
    setTimeout(f){ return 1; }, clearTimeout(){}, setInterval(){ return 1; }, clearInterval(){},
    localStorage: { getItem(){ return null; }, setItem(){}, removeItem(){} },
    location: { hash: "#" + hash, href: "office.html" },
    addEventListener(){}, removeEventListener(){},
    matchMedia(){ return { matches:false, addEventListener(){} }; },
    URL: { createObjectURL(){ return "blob:x"; }, revokeObjectURL(){} },
    Blob: function(){}, alert(){}, confirm(){ return true; }, prompt(){ return ""; },
    navigator: { clipboard: { writeText(){ return Promise.resolve(); } } },
    document: {
      getElementById: byId,
      querySelector: sel => byId("q:" + sel),
      querySelectorAll: () => [],
      createElement: () => mkEl(),
      addEventListener(){}, body: mkEl(), documentElement: mkEl(),
    },
    window: {},
  };
  G.globalThis = G;
  const vm = require("vm");
  const ctx = vm.createContext(G);
  try {
    vm.runInContext(dataJs, ctx, { filename: "office-data.js" });
    for (const [i, b] of blocks.entries()) vm.runInContext(b, ctx, { filename: "inline" + i });
    const main = reg.get("q:#main") || byId("q:#main");
    const len = (main._html || "").length;
    console.log(`[${hash}] OK — #main length ${len}${len < 50 ? " ⚠ (빈 화면 가능)" : ""}`);
  } catch (e) {
    console.log(`[${hash}] THROW — ${e.message}`);
    console.log("   " + (e.stack || "").split("\n")[1]);
  }
}
for (const t of ["board", "movement", "ops", "customers", "data"]) runTab(t);
