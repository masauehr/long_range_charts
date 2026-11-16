// 長期予報用 統計図ビューア・標準表示（Vanilla JS）。
// 数値モデル天気図の標準表示（nwp_chart_web の通常版）に合わせた操作: 時間軸＝「期間」（週1〜週4・月1〜月4・3か月 など）を
// ◀ ▶ ・スライダー・再生で動かし、↑↓で変数を切り替える。2系列比較（CFS と CPS4 など）・初期値の前後切替・URL で状態を保存。
// 画像は ../output/ を相対参照（output/ は git 除外）。公開は NOTICE.md の確認後。
"use strict";

const VAR_ORDER = ["t2m", "prate", "z500", "sst", "pot5"];
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L5", "L6", "L2-4", "L1-3"];
const IMG_DIR = "../output/";

let M = null;
let timer = null;
const S = { compare: false, sync: true, size: "fit", speed: 1200,
            L: { series: null, init: null, var: "t2m", period: null, region: "asia" },
            R: { series: null, init: null, var: "t2m", period: null, region: "asia" } };

const $ = (id) => document.getElementById(id);
const sortBy = (arr, order) => [...arr].sort((a, b) => ((order.indexOf(a) + 99) % 99) - ((order.indexOf(b) + 99) % 99));
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

// ---------------------------------------------------------------- 選べる値
const seriesOf = (id) => M.series.find((s) => s.id === id) || M.series[0];
const initOf = (P) => { const s = seriesOf(P.series); return s.inits.find((i) => i.init === P.init) || s.inits[0]; };
const varsOf = (P) => sortBy(Object.keys(initOf(P).vars), VAR_ORDER);
const periodsOf = (P) => sortBy(Object.keys(initOf(P).periods), PERIOD_ORDER);
const fileOf = (P, v = P.var, p = P.period, r = P.region) => initOf(P).files[`${v}|${p}|${r}`];

function fix(P) {
  P.series = seriesOf(P.series).id;
  P.init = initOf(P).init;
  if (!varsOf(P).includes(P.var)) P.var = varsOf(P)[0];
  if (!periodsOf(P).includes(P.period)) P.period = periodsOf(P)[0];
  if (!M.regions[P.region]) P.region = Object.keys(M.regions)[0];
}

// 右は左に合わせる: 変数・領域は同じに、期間は「表示する期間のラベル（月の範囲）」が同じものを選ぶ（無ければ番号が近いもの）
function syncRight() {
  if (!S.compare) return;
  fix(S.R);
  if (!S.sync) return;
  S.R.var = S.L.var;
  S.R.region = S.L.region;
  fix(S.R);
  const lab = initOf(S.L).periods[S.L.period];
  const itR = initOf(S.R);
  const same = periodsOf(S.R).find((p) => itR.periods[p] === lab);
  if (same) S.R.period = same;
}

// ---------------------------------------------------------------- 描画
function option(sel, items, current) {
  sel.replaceChildren(...items.map(([v, t]) => { const o = el("option", null, t); o.value = v; o.selected = v === current; return o; }));
}
function segButtons(node, items, current, onPick) {
  node.replaceChildren(...items.map(([v, t]) => {
    const b = el("button", null, t);
    b.type = "button";
    b.setAttribute("aria-pressed", String(v === current));
    b.addEventListener("click", () => onPick(v));
    return b;
  }));
}

function figureNode(P, name) {
  const it = initOf(P);
  const box = el("section", `panel size-${S.size}`);
  box.setAttribute("aria-label", name);
  const cap = el("div", "cap");
  cap.append(el("strong", null, seriesOf(P.series).label), el("span", null, ` ／ ${it.label} ／ ${it.vars[P.var]} ／ ${it.periods[P.period]} ／ ${M.regions[P.region]}`));
  box.appendChild(cap);
  box.appendChild(el("div", "note", seriesOf(P.series).note));
  const fig = el("div", "figure");
  const f = fileOf(P);
  if (f) {
    const img = el("img");
    img.src = IMG_DIR + f;
    img.alt = `${it.label} ${it.vars[P.var]} ${it.periods[P.period]} ${M.regions[P.region]}`;
    img.addEventListener("error", () => img.replaceWith(el("div", "msg", `画像を読み込めませんでした: ${f}`)));
    fig.appendChild(img);
  } else {
    fig.appendChild(el("div", "msg", "この組み合わせの図はありません。"));
  }
  box.appendChild(fig);
  return box;
}

function thumbNode(P, v, p, label, active) {
  const f = fileOf(P, v, p);
  const b = el("button", "thumb");
  b.type = "button";
  b.setAttribute("aria-pressed", String(active));
  if (f) { const i = el("img"); i.src = IMG_DIR + f; i.loading = "lazy"; i.alt = ""; b.appendChild(i); }
  b.appendChild(el("span", null, label));
  b.addEventListener("click", () => { if (v !== P.var) S.L.var = v; if (p !== P.period) S.L.period = p; change(); });
  return b;
}

function render() {
  const L = S.L, it = initOf(L);
  option($("seriesSel"), M.series.map((s) => [s.id, s.label]), L.series);
  option($("initSel"), seriesOf(L.series).inits.map((i) => [i.init, i.label]), L.init);
  segButtons($("regionBtns"), Object.entries(M.regions), L.region, (r) => { L.region = r; change(); });
  $("compare").checked = S.compare;
  $("rightRow").hidden = !S.compare;
  if (S.compare) {
    option($("seriesSel2"), M.series.map((s) => [s.id, s.label]), S.R.series);
    option($("initSel2"), seriesOf(S.R.series).inits.map((i) => [i.init, i.label]), S.R.init);
    $("sync").checked = S.sync;
  }
  $("sizeSel").value = S.size;
  $("speedSel").value = String(S.speed);
  $("updated").textContent = `一覧の更新: ${M.generated}`;

  // 変数タブ
  const tabs = $("varTabs");
  tabs.replaceChildren(...varsOf(L).map((v) => {
    const b = el("button", null, it.vars[v]);
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(v === L.var));
    b.addEventListener("click", () => { L.var = v; change(); });
    return b;
  }));

  // 図
  const panels = $("panels");
  panels.classList.toggle("two", S.compare);
  panels.replaceChildren(figureNode(L, S.compare ? "左の図" : "図"), ...(S.compare ? [figureNode(S.R, "右の図")] : []));

  // 期間の操作
  const ps = periodsOf(L), idx = ps.indexOf(L.period);
  const sl = $("slider");
  sl.max = String(ps.length - 1);
  sl.value = String(idx);
  $("btnFirst").disabled = $("btnPrev").disabled = idx <= 0;
  $("btnLast").disabled = $("btnNext").disabled = idx >= ps.length - 1;
  $("btnPlay").textContent = timer ? "⏸" : "▶";
  $("timeInfo").textContent = `${idx + 1} / ${ps.length}　${L.period}　${it.periods[L.period]}`;
  const f = fileOf(L);
  const dl = $("dlLink");
  if (f) { dl.href = IMG_DIR + f; dl.download = f; dl.hidden = false; } else dl.hidden = true;

  // サムネイル（同じ期間の変数・同じ変数の期間）
  $("thumbsVar").replaceChildren(...varsOf(L).map((v) => thumbNode(L, v, L.period, it.vars[v], v === L.var)));
  $("thumbsPer").replaceChildren(...ps.map((p) => thumbNode(L, L.var, p, `${p}　${it.periods[p]}`, p === L.period)));
}

// ---------------------------------------------------------------- 状態
function change() {
  fix(S.L);
  syncRight();
  save();
  render();
}
function step(d) {
  const ps = periodsOf(S.L), i = ps.indexOf(S.L.period) + d;
  if (i >= 0 && i < ps.length) { S.L.period = ps[i]; change(); return true; }
  return false;
}
function setIdx(i) { const ps = periodsOf(S.L); S.L.period = ps[Math.max(0, Math.min(ps.length - 1, i))]; change(); }
function stepVar(d) {
  const vs = varsOf(S.L), i = vs.indexOf(S.L.var) + d;
  if (i >= 0 && i < vs.length) { S.L.var = vs[i]; change(); }
}
function stepInit(d) {                 // d=+1 は古い方（一覧は新しい順）
  const list = seriesOf(S.L.series).inits, i = list.findIndex((x) => x.init === S.L.init) + d;
  if (i >= 0 && i < list.length) { S.L.init = list[i].init; change(); }
}
function togglePlay() {
  if (timer) { clearInterval(timer); timer = null; render(); return; }
  if (periodsOf(S.L).indexOf(S.L.period) >= periodsOf(S.L).length - 1) setIdx(0);
  timer = setInterval(() => { if (!step(1)) { clearInterval(timer); timer = null; render(); } }, S.speed);
  render();
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
  const bl = $("boardLink");
  bl.href = `board.html#s=${encodeURIComponent(S.L.series)}&i=${S.L.init}&r=${S.L.region}`;
}
function load() {
  const p = new URLSearchParams(location.hash.slice(1));
  const g = (k, d) => p.get(k) || d;
  S.L = { series: g("s", M.series[0].id), init: g("i", null), var: g("v", "t2m"), period: g("p", null), region: g("r", "asia") };
  S.size = ["fit", "wide", "80"].includes(g("z", "")) ? g("z", "fit") : "fit";
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
  $("seriesSel").addEventListener("change", (e) => { S.L.series = e.target.value; S.L.init = null; change(); });
  $("initSel").addEventListener("change", (e) => { S.L.init = e.target.value; change(); });
  $("seriesSel2").addEventListener("change", (e) => { S.R.series = e.target.value; S.R.init = null; change(); });
  $("initSel2").addEventListener("change", (e) => { S.R.init = e.target.value; change(); });
  $("compare").addEventListener("change", (e) => { S.compare = e.target.checked; change(); });
  $("sync").addEventListener("change", (e) => { S.sync = e.target.checked; change(); });
  $("sizeSel").addEventListener("change", (e) => { S.size = e.target.value; change(); });
  $("speedSel").addEventListener("change", (e) => { S.speed = Number(e.target.value); if (timer) { togglePlay(); togglePlay(); } else render(); });
  $("btnFirst").addEventListener("click", () => setIdx(0));
  $("btnPrev").addEventListener("click", () => step(-1));
  $("btnNext").addEventListener("click", () => step(1));
  $("btnLast").addEventListener("click", () => setIdx(99));
  $("btnPlay").addEventListener("click", togglePlay);
  $("slider").addEventListener("input", (e) => setIdx(Number(e.target.value)));
  document.addEventListener("keydown", (e) => {
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName) && e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (k === "ArrowLeft") step(-1);
    else if (k === "ArrowRight") step(1);
    else if (k === "ArrowUp") stepVar(-1);
    else if (k === "ArrowDown") stepVar(1);
    else if (k === "Home") setIdx(0);
    else if (k === "End") setIdx(99);
    else if (k === " ") togglePlay();
    else if (k === "[") stepInit(1);
    else if (k === "]") stepInit(-1);
    else if (k === "r" || k === "R") { const rs = Object.keys(M.regions); S.L.region = rs[(rs.indexOf(S.L.region) + 1) % rs.length]; change(); }
    else if (k === "c" || k === "C") { S.compare = !S.compare; change(); }
    else return;
    e.preventDefault();
  });
  change();
}
main();
