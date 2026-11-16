// 画用紙版: 1つの系列・初期値・領域について、変数（行）×期間（列）の図を一度に並べる。クリックで標準表示を開く。
"use strict";

const VAR_ORDER = ["t2m", "prate", "z500", "sst", "pot5"];
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L5", "L6", "L2-4", "L1-3"];
let IMG_DIR = "../output/";             // 公開版は manifest の imgdir（"output/"）で上書き
let M = null;
const S = { series: null, init: null, region: "asia", w: 300 };

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const sortBy = (arr, order) => [...arr].sort((a, b) => ((order.indexOf(a) + 99) % 99) - ((order.indexOf(b) + 99) % 99));
const seriesOf = () => M.series.find((s) => s.id === S.series) || M.series[0];
const initOf = () => { const s = seriesOf(); return s.inits.find((i) => i.init === S.init) || s.inits[0]; };

function fix() {
  S.series = seriesOf().id;
  S.init = initOf().init;
  if (!M.regions[S.region]) S.region = Object.keys(M.regions)[0];
}
function option(sel, items, current) {
  sel.replaceChildren(...items.map(([v, t]) => { const o = el("option", null, t); o.value = v; o.selected = v === current; return o; }));
}

function render() {
  fix();
  const it = initOf();
  option($("seriesSel"), M.series.map((s) => [s.id, s.label]), S.series);
  option($("initSel"), seriesOf().inits.map((i) => [i.init, i.label]), S.init);
  $("regionBtns").replaceChildren(...Object.entries(M.regions).map(([r, t]) => {
    const b = el("button", null, t);
    b.type = "button";
    b.setAttribute("aria-pressed", String(r === S.region));
    b.addEventListener("click", () => { S.region = r; render(); });
    return b;
  }));
  $("sizeRange").value = String(S.w);
  $("updated").textContent = `一覧の更新: ${M.generated}`;
  $("note").textContent = seriesOf().note;
  $("stdLink").href = `index.html#s=${encodeURIComponent(S.series)}&i=${S.init}&r=${S.region}`;

  const vars = sortBy(Object.keys(it.vars), VAR_ORDER), pers = sortBy(Object.keys(it.periods), PERIOD_ORDER);
  const grid = el("div", "bgrid");
  grid.style.gridTemplateColumns = `7em repeat(${pers.length}, ${S.w}px)`;
  grid.appendChild(el("div", "bhead"));
  for (const p of pers) grid.appendChild(el("div", "bhead", `${p}　${it.periods[p]}`));
  for (const v of vars) {
    grid.appendChild(el("div", "bhead bvar", it.vars[v]));
    for (const p of pers) {
      const f = it.files[`${v}|${p}|${S.region}`];
      const cell = el("a", "bcell");
      cell.href = `index.html#s=${encodeURIComponent(S.series)}&i=${S.init}&v=${v}&p=${p}&r=${S.region}`;
      if (f) { const i = el("img"); i.src = IMG_DIR + f; i.loading = "lazy"; i.alt = `${it.vars[v]} ${it.periods[p]}`; cell.appendChild(i); }
      else cell.appendChild(el("span", "msg", "なし"));
      grid.appendChild(cell);
    }
  }
  $("board").replaceChildren(grid);
  try { history.replaceState(null, "", `#s=${encodeURIComponent(S.series)}&i=${S.init}&r=${S.region}&w=${S.w}`); } catch (e) { /* 無視 */ }
}

async function main() {
  try { M = await (await fetch("manifest.json", { cache: "no-store" })).json(); }
  catch (e) { $("board").textContent = "manifest.json を読めません。python make_web.py を実行し、プロジェクト直下で python -m http.server を起動してください。"; return; }
  if (M.imgdir) IMG_DIR = M.imgdir;
  if (!M.series.some((x) => x.id === "cps4")) document.querySelectorAll(".c3s").forEach((e) => e.remove());   // CPS4 を載せない公開版
  if (!M.series.length) { $("board").textContent = "図がありません。"; return; }
  const p = new URLSearchParams(location.hash.slice(1));
  S.series = p.get("s") || M.series[0].id;
  S.init = p.get("i");
  S.region = p.get("r") || "asia";
  S.w = Number(p.get("w")) || 300;
  $("seriesSel").addEventListener("change", (e) => { S.series = e.target.value; S.init = null; render(); });
  $("initSel").addEventListener("change", (e) => { S.init = e.target.value; render(); });
  $("sizeRange").addEventListener("input", (e) => { S.w = Number(e.target.value); render(); });
  render();
}
main();
