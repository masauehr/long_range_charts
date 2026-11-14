// 長期予報用 統計図ビューア（Vanilla JS）。manifest.json（make_web.py が output/ から作る）を読み、
// 系列・初期値・変数・期間・領域を切り替える。2つ並べて比較（CFS と CPS4 など）もできる。
// 画像は ../output/ を相対参照（output/ は git 除外）。公開は Phase 5・NOTICE.md の確認後。
"use strict";

const VAR_ORDER = ["t2m", "prate", "z500", "sst", "pot5"];
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L2-4"];
const SIZES = [["fit", "画面に収める"], ["wide", "幅いっぱい"], ["80", "80%"], ["60", "60%"]];
const IMG_DIR = "../output/";

let M = null;
const S = { size: "fit", compare: false, sync: true,
            L: { series: null, init: null, var: null, period: null, region: "asia" },
            R: { series: null, init: null, var: null, period: null, region: "asia" } };

const $ = (id) => document.getElementById(id);
const sortBy = (arr, order) => [...arr].sort((a, b) => (order.indexOf(a) + 99) % 99 - (order.indexOf(b) + 99) % 99);

// ---------------------------------------------------------------- 選べる値
const seriesOf = (id) => M.series.find((s) => s.id === id);
const initOf = (P) => { const s = seriesOf(P.series); return s.inits.find((i) => i.init === P.init) || s.inits[0]; };
const varsOf = (P) => sortBy(Object.keys(initOf(P).vars), VAR_ORDER);
const periodsOf = (P) => sortBy(Object.keys(initOf(P).periods), PERIOD_ORDER);
const fileOf = (P) => initOf(P).files[`${P.var}|${P.period}|${P.region}`];

function fix(P) {
  if (!seriesOf(P.series)) P.series = M.series[0].id;
  const it = initOf(P);
  P.init = it.init;
  if (!varsOf(P).includes(P.var)) P.var = varsOf(P)[0];
  if (!periodsOf(P).includes(P.period)) P.period = periodsOf(P)[0];
  if (!M.regions[P.region]) P.region = Object.keys(M.regions)[0];
}

// ---------------------------------------------------------------- 部品
function seg(items, current, onPick, label) {
  const d = document.createElement("div");
  d.className = "seg";
  d.setAttribute("role", "group");
  d.setAttribute("aria-label", label);
  for (const [value, text] of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.setAttribute("aria-pressed", String(value === current));
    b.addEventListener("click", () => onPick(value));
    d.appendChild(b);
  }
  return d;
}
function row(labelText, node) {
  const r = document.createElement("div");
  r.className = "row";
  const l = document.createElement("span");
  l.className = "lab";
  l.textContent = labelText;
  r.append(l, node);
  return r;
}

function panelNode(P, name) {
  const it = initOf(P);
  const box = document.createElement("section");
  box.className = `panel size-${S.size}`;
  box.setAttribute("aria-label", name);

  const sel = document.createElement("select");
  sel.setAttribute("aria-label", `${name}の系列`);
  for (const s of M.series) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.label;
    o.selected = s.id === P.series;
    sel.appendChild(o);
  }
  sel.addEventListener("change", () => { P.series = sel.value; change(P === S.L); });
  const initSel = document.createElement("select");
  initSel.setAttribute("aria-label", `${name}の初期値`);
  for (const i of seriesOf(P.series).inits) {
    const o = document.createElement("option");
    o.value = i.init;
    o.textContent = i.label;
    o.selected = i.init === P.init;
    initSel.appendChild(o);
  }
  initSel.addEventListener("change", () => { P.init = initSel.value; change(P === S.L); });
  const top = document.createElement("div");
  top.className = "row";
  top.append(sel, initSel);
  box.appendChild(top);

  const syncLocked = P === S.R && S.sync;      // 右は左に合わせるとき、変数・領域は選べない
  const vars = varsOf(P).map((v) => [v, it.vars[v]]);
  const regs = Object.entries(M.regions);
  const pers = periodsOf(P).map((p) => [p, it.periods[p]]);
  const vs = row("変数", seg(vars, P.var, (v) => { P.var = v; change(P === S.L); }, "変数"));
  const rs = row("領域", seg(regs, P.region, (r) => { P.region = r; change(P === S.L); }, "領域"));
  if (syncLocked) for (const r of [vs, rs]) r.querySelectorAll("button").forEach((b) => (b.disabled = true));
  box.append(vs, row("期間", seg(pers, P.period, (p) => { P.period = p; change(false); }, "期間")), rs);

  const note = document.createElement("div");
  note.className = "note";
  note.textContent = seriesOf(P.series).note;
  box.appendChild(note);

  const fig = document.createElement("div");
  fig.className = "figure";
  const f = fileOf(P);
  if (f) {
    const img = document.createElement("img");
    img.src = IMG_DIR + f;
    img.alt = `${it.label} ${it.vars[P.var]} ${it.periods[P.period]} ${M.regions[P.region]}`;
    img.addEventListener("error", () => {
      const m = document.createElement("div");
      m.className = "msg";
      m.textContent = `画像を読み込めませんでした: ${f}（output/ に図があるか確認してください）`;
      img.replaceWith(m);
    });
    fig.appendChild(img);
  } else {
    const m = document.createElement("div");
    m.className = "msg";
    m.textContent = "この組み合わせの図はありません。";
    fig.appendChild(m);
  }
  box.appendChild(fig);
  return box;
}

// ---------------------------------------------------------------- 状態
function syncRight() {
  if (!S.compare) return;
  if (S.sync) {                                   // 変数・領域は左に合わせる（右の系列に無い変数は先頭へ）
    S.R.var = S.L.var;
    S.R.region = S.L.region;
  }
  fix(S.R);
}
function change() {
  fix(S.L);
  syncRight();
  save();
  render();
}
function render() {
  const panels = $("panels");
  panels.replaceChildren();
  panels.classList.toggle("two", S.compare);
  panels.appendChild(panelNode(S.L, S.compare ? "左の図" : "図"));
  if (S.compare) panels.appendChild(panelNode(S.R, "右の図"));
  $("syncwrap").hidden = !S.compare;
  $("compare").checked = S.compare;
  $("sync").checked = S.sync;
  const sz = $("sizes");
  sz.replaceChildren(...seg(SIZES, S.size, (v) => { S.size = v; save(); render(); }, "画像の大きさ").children);
  $("updated").textContent = `一覧の更新: ${M.generated}`;
}

// URL の # に状態を保存（再読み込みやリンク共有で同じ図に戻れる）
function save() {
  const p = new URLSearchParams({ s: S.L.series, i: S.L.init, v: S.L.var, p: S.L.period, r: S.L.region, z: S.size });
  if (S.compare) {
    p.set("c", "1");
    p.set("y", S.sync ? "1" : "0");
    for (const [k, v] of [["s2", S.R.series], ["i2", S.R.init], ["v2", S.R.var], ["p2", S.R.period], ["r2", S.R.region]]) p.set(k, v);
  }
  try { history.replaceState(null, "", "#" + p.toString()); } catch (e) { /* file:// 等では無視 */ }
}
function load() {
  const p = new URLSearchParams(location.hash.slice(1));
  const g = (k, d) => p.get(k) || d;
  S.L = { series: g("s", M.series[0].id), init: g("i", null), var: g("v", "t2m"), period: g("p", null), region: g("r", "asia") };
  S.size = SIZES.some((x) => x[0] === g("z", "")) ? g("z", "fit") : "fit";
  S.compare = g("c", "0") === "1";
  S.sync = g("y", "1") === "1";
  const last = M.series[M.series.length - 1];
  S.R = { series: g("s2", S.L.series === last.id ? M.series[0].id : last.id), init: g("i2", null), var: g("v2", S.L.var),
          period: g("p2", null), region: g("r2", S.L.region) };
  
}

async function main() {
  try {
    M = await (await fetch("manifest.json", { cache: "no-store" })).json();
  } catch (e) {
    $("panels").textContent = "manifest.json を読めません。python make_web.py を実行し、プロジェクト直下で python -m http.server を起動して /web/ を開いてください。";
    return;
  }
  if (!M.series.length) { $("panels").textContent = "図がありません（output/ を確認してください）。"; return; }
  load();
  $("compare").addEventListener("change", (e) => { S.compare = e.target.checked; change(); });
  $("sync").addEventListener("change", (e) => { S.sync = e.target.checked; change(); });
  document.addEventListener("keydown", (e) => {                       // ← → で左の図の期間を前後へ
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const ps = periodsOf(S.L);
    const i = ps.indexOf(S.L.period) + (e.key === "ArrowRight" ? 1 : -1);
    if (i >= 0 && i < ps.length) { S.L.period = ps[i]; change(); }
  });
  change();
}
main();
