// 長期予報用 統計図ビューア・標準表示（Vanilla JS）。
// 数値モデル天気図の標準表示（nwp_chart_web の通常版）に合わせた操作: 時間軸＝「期間」（週1〜週4・月1〜月4・3か月 など）を
// ◀ ▶ ・スライダー・再生で動かし、↑↓で変数を切り替える。2系列比較（CFS と CPS4 など）・初期値の前後切替・URL で状態を保存。
// 画像は ../output/ を相対参照（output/ は git 除外）。公開は NOTICE.md の確認後。
"use strict";

const VAR_ORDER = ["t2m", "prate", "z500", "psi850", "psi200", "chi200", "olr", "sst", "pot5"];
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L5", "L6", "L2-4", "L1-3"];
let IMG_DIR = "../output/";             // 公開版は manifest の imgdir（"output/"）で上書き

let M = null;
let timer = null;
const S = { mode: "fc", compare: false, sync: true, size: "fit", speed: 1200,
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
const fileOf = (P, v = P.var, p = P.period, r = P.region) => {
  const it = initOf(P), k = `${v}|${p}|${r}`;
  return S.mode === "clim" ? (it.clim_files || {})[k] : it.files[k];
};

function fix(P) {
  P.series = seriesOf(P.series).id;
  P.init = initOf(P).init;
  if (!varsOf(P).includes(P.var)) P.var = varsOf(P)[0];
  if (!periodsOf(P).includes(P.period)) P.period = periodsOf(P)[0];
  if (!M.regions[P.region]) P.region = Object.keys(M.regions)[0];
  if (!fileOf(P)) {                                   // 選んだ領域の図が無い（例: 気象庁形式は一部の変数だけ）ときは、図がある領域へ移る
    const alt = Object.keys(M.regions).find((r) => fileOf(P, P.var, P.period, r));
    if (alt) P.region = alt;
  }
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
  if (S.mode === "clim") box.appendChild(el("div", "note", "気候値（平年）の図です。予報ではなく、予報を比べるための基準です。境目（下位1/3・上位1/3）を超えると「低い」「高い」側になります。"));
  const fig = el("div", "figure");
  const f = fileOf(P);
  if (f) {
    const img = el("img");
    img.src = IMG_DIR + f;
    img.alt = `${it.label} ${it.vars[P.var]} ${it.periods[P.period]} ${M.regions[P.region]}`;
    img.addEventListener("error", () => img.replaceWith(el("div", "msg", `画像を読み込めませんでした: ${f}`)));
    fig.appendChild(img);
  } else {
    fig.appendChild(el("div", "msg", S.mode === "clim" ? "この組み合わせの気候値の図はありません（最新の初期日だけ作っています）。" : "この組み合わせの図はありません。"));
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
  segButtons($("regionBtns"), Object.entries(M.regions).filter(([r]) => r === L.region || fileOf(L, L.var, L.period, r)), L.region, (r) => { L.region = r; change(); });
  segButtons($("modeBtns"), [["fc", "予報（偏差・確率）"], ["clim", "気候値（平年）"]], S.mode, (m) => { S.mode = m; change(); });
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
  renderPoints();
}

// ---------------------------------------------------------------- 地点の数値（気候値・境目・予報）
const CITIES = [["札幌", 43.06, 141.35], ["青森", 40.82, 140.74], ["仙台", 38.27, 140.87], ["東京", 35.69, 139.69], ["新潟", 37.92, 139.04],
  ["長野", 36.65, 138.18], ["金沢", 36.56, 136.66], ["名古屋", 35.18, 136.91], ["大阪", 34.69, 135.5], ["広島", 34.4, 132.46],
  ["松江", 35.47, 133.05], ["高知", 33.56, 133.53], ["福岡", 33.59, 130.4], ["鹿児島", 31.6, 130.56], ["那覇", 26.21, 127.68],
  ["宮古島", 24.8, 125.28], ["石垣島", 24.34, 124.16], ["ソウル", 37.57, 126.98], ["ウラジオストク", 43.12, 131.89], ["北京", 39.9, 116.41],
  ["上海", 31.23, 121.47], ["台北", 25.03, 121.57], ["香港", 22.32, 114.17]];
const PT = { city: "東京", lat: 35.69, lon: 139.69, cache: {} };
function nearest(arr, v) { let b = 0; arr.forEach((x, i) => { if (Math.abs(x - v) < Math.abs(arr[b] - v)) b = i; }); return b; }
const fmt = (v, nd) => (v == null ? "—" : Number(v).toFixed(nd));
async function renderPoints() {
  const box = $("pointTable");
  if (!$("pointBox").open) return;
  const L = S.L, it = initOf(L);
  const sel = $("citySel");
  if (!sel.options.length) {
    sel.replaceChildren(...CITIES.map(([n]) => { const o = el("option", null, n); o.value = n; return o; }), Object.assign(el("option", null, "（緯度・経度を指定）"), { value: "" }));
    sel.value = PT.city;
    $("latIn").value = PT.lat; $("lonIn").value = PT.lon;
  }
  if (!it.points) { box.textContent = L.series === "cfs_week_lag" ? "ラグ18メンバー版は地点の数値に対応していません（「CFSv2 週平均（4メンバー）」を選んでください）。" : "この初期日の地点の数値はありません（最新の初期日だけ作っています）。"; return; }
  if (!PT.cache[it.points]) {
    box.textContent = "読み込み中…";
    try { PT.cache[it.points] = await (await fetch(IMG_DIR + it.points)).json(); } catch (e) { box.textContent = "地点の数値を読めません。"; return; }
  }
  const d = PT.cache[it.points], v = d.vars[L.var];
  if (!v) { box.textContent = "この変数の地点の数値はありません。"; return; }
  const i = nearest(d.lat, PT.lat), j = nearest(d.lon, PT.lon), k = i * d.lon.length + j;
  const inside = PT.lat >= d.lat[d.lat.length - 1] - 1.25 && PT.lat <= d.lat[0] + 1.25 && PT.lon >= d.lon[0] - 1.25 && PT.lon <= d.lon[d.lon.length - 1] + 1.25;
  if (!inside) { box.textContent = "この地点は範囲外です（東アジア: 北緯8〜62°・東経95〜175°）。"; return; }
  const nd = L.var === "prate" ? 2 : 1, u = v.unit;
  const t = el("table"), head = el("tr");
  for (const h of ["期間", `気候値(${u})`, `下位1/3の境目(${u})`, `上位1/3の境目(${u})`, `今回の予報(${u})`, `偏差(${u})`, "低い側の確率", "高い側の確率"]) head.appendChild(el("th", null, h));
  t.appendChild(el("thead")).appendChild(head);
  const body = el("tbody");
  for (const p of periodsOf(L)) {
    const r = v.periods[p];
    if (!r) continue;
    const tr = el("tr");
    if (p === L.period) tr.className = "cur";
    const cells = [`${p}　${r.label}`, fmt(r.mean[k], nd), fmt(r.t33[k], nd), fmt(r.t67[k], nd), fmt(r.fc[k], nd),
                   (r.anom[k] >= 0 ? "+" : "") + fmt(r.anom[k], nd), r.pl[k] == null ? "—" : `${r.pl[k]}%`, r.pu[k] == null ? "—" : `${r.pu[k]}%`];
    cells.forEach((c, n) => tr.appendChild(el("td", n === 0 ? "lab" : null, c)));
    body.appendChild(tr);
  }
  t.appendChild(body);
  box.replaceChildren(el("p", "muted", `${PT.city || "指定した地点"}（北緯${PT.lat}°・東経${PT.lon}°）に最も近い格子: 北緯${d.lat[i]}°・東経${d.lon[j]}°。${v.label}。`),
    t, el("p", "muted", "「予報」が上位1/3の境目を超えると「高い」側、下位1/3の境目を下回ると「低い」側になります。" + (periodsOf(L).some((p) => v.periods[p] && v.periods[p].alpha == null) ? "この変数の確率は、観測との照合が未実施の期間があり、未補正（自信過剰の可能性）です。" : "確率は図と同じく、観測との照合で縮小した値です（係数は図の下端）。") + "気象庁の観測所の平年値とは別物です（モデルの約250km四方の格子の値で、海を含みます）。"));
  drawDist(d, k, v, L, it);
}

// ---------------------------------------------------------------- 分布図（過去の分布と今回の予報メンバー）
const DC = {};
async function drawDist(pts, k, v, L, it) {
  const box = $("distBox"), cv = $("distCanvas");
  if (!it.dist) { box.hidden = true; return; }
  if (!DC[it.dist]) {
    try { DC[it.dist] = await (await fetch(IMG_DIR + it.dist)).json(); } catch (e) { box.hidden = true; return; }
  }
  const D = DC[it.dist], vd = D.vars[L.var];
  if (!vd) { box.hidden = true; return; }
  box.hidden = false;
  const per = periodsOf(L).filter((p) => vd[p]);
  const sel = $("distPer");
  if (sel.dataset.sig !== per.join()) {
    sel.replaceChildren(...per.map((p) => { const o = el("option", null, p + "　" + it.periods[p]); o.value = p; return o; }));
    sel.dataset.sig = per.join();
    sel.dataset.user = "";
  }
  if (!sel.dataset.user || !per.includes(sel.value)) sel.value = per.includes(L.period) ? L.period : per[0];     // 自分で選ぶまでは、表示中の期間に合わせる
  const p = sel.value, r = vd[p], pr = v.periods[p], nb = D.nb;
  const lo = r.lo[k], hi = r.hi[k];
  const cc = r.cc.slice(k * nb, (k + 1) * nb), fc = r.fc.slice(k * nb, (k + 1) * nb);
  const sc = cc.reduce((a, b) => a + b, 0), sf = fc.reduce((a, b) => a + b, 0);
  const css = getComputedStyle(document.documentElement);
  const MUTED = css.getPropertyValue("--muted").trim() || "#666", LINE = css.getPropertyValue("--line").trim() || "#ccc";
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height, pl = 46, prr = 12, pt = 30, pb = 40;
  ctx.clearRect(0, 0, W, H);
  ctx.font = "12px sans-serif";
  if (!sc || !(hi > lo)) { ctx.fillStyle = MUTED; ctx.fillText("この地点の分布はありません。", 20, 40); $("distText").textContent = ""; return; }
  const X = (val) => pl + ((val - lo) / (hi - lo)) * (W - pl - prr);
  const maxv = Math.max(...cc.map((c) => c / sc), ...(sf ? fc.map((c) => c / sf) : [0])) || 1;
  const Y = (f) => H - pb - (f / maxv) * (H - pt - pb);
  const bw = (W - pl - prr) / nb;
  ctx.strokeStyle = LINE; ctx.beginPath(); ctx.moveTo(pl, H - pb); ctx.lineTo(W - prr, H - pb); ctx.stroke();
  cc.forEach((c, i) => { ctx.fillStyle = "rgba(140,145,150,0.55)"; ctx.fillRect(pl + i * bw + 1, Y(c / sc), bw - 2, H - pb - Y(c / sc)); });
  if (sf) fc.forEach((c, i) => { if (c) { ctx.fillStyle = "rgba(214,60,50,0.55)"; ctx.fillRect(pl + i * bw + bw * 0.2, Y(c / sf), bw * 0.6, H - pb - Y(c / sf)); } });
  const vline = (val, color, w, dash, label, ypos) => {
    if (val == null || !(val >= lo && val <= hi)) return;
    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath(); ctx.moveTo(X(val), pt - 4); ctx.lineTo(X(val), H - pb); ctx.stroke();
    ctx.setLineDash([]); ctx.lineWidth = 1;
    ctx.fillStyle = color; ctx.textAlign = "center"; ctx.fillText(label, X(val), ypos); ctx.textAlign = "left";
  };
  vline(pr.t33[k], "#2b6cb0", 1.5, [5, 4], "下位1/3", 12);
  vline(pr.t67[k], "#c05621", 1.5, [5, 4], "上位1/3", 12);
  vline(pr.mean[k], MUTED, 1.5, [], "気候値", 24);
  vline(pr.fc[k], "#d63c32", 2.5, [], "予報(平均)", 24);
  ctx.fillStyle = MUTED; ctx.textAlign = "center";
  for (let t = 0; t <= 4; t++) { const val = lo + ((hi - lo) * t) / 4; ctx.fillText(val.toFixed(L.var === "prate" ? 2 : 1), X(val), H - pb + 16); }
  ctx.fillText(v.label + "（" + v.unit + "）", W / 2, H - 6);
  ctx.textAlign = "left";
  let below = 0;
  cc.forEach((c, i) => {
    const a = lo + (i * (hi - lo)) / nb, b = a + (hi - lo) / nb;
    if (pr.fc[k] >= b) below += c; else if (pr.fc[k] > a) below += (c * (pr.fc[k] - a)) / (b - a);
  });
  const pct = Math.round((below / sc) * 100);
  const where = pct >= 67 ? "上位1/3の側（「高い」側）" : pct <= 33 ? "下位1/3の側（「低い」側）" : "真ん中あたり（「平年並」側）";
  $("distText").textContent = "今回の予報（平均 " + pr.fc[k] + " " + v.unit + "）は、過去の分布（" + r.n + "個のサンプル）の下から約" + pct + "%の位置で、" + where + "です。予報のメンバーは" + r.m + "個。"
    + (r.m <= 4 ? "メンバーが少ないので、赤い棒はとびとびになります。" : "");
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
  if (S.mode === "clim") p.set("m", "clim");
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
  S.mode = g("m", "fc") === "clim" ? "clim" : "fc";
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
  if (M.imgdir) IMG_DIR = M.imgdir;
  if (!M.series.some((x) => x.id === "cps4")) document.querySelectorAll(".c3s").forEach((e) => e.remove());   // CPS4 を載せない公開版
  if (!M.series.length) { $("panels").textContent = "図がありません（output/ を確認してください）。"; return; }
  load();
  $("seriesSel").addEventListener("change", (e) => { S.L.series = e.target.value; S.L.init = null; change(); });
  $("initSel").addEventListener("change", (e) => { S.L.init = e.target.value; change(); });
  $("seriesSel2").addEventListener("change", (e) => { S.R.series = e.target.value; S.R.init = null; change(); });
  $("initSel2").addEventListener("change", (e) => { S.R.init = e.target.value; change(); });
  $("compare").addEventListener("change", (e) => { S.compare = e.target.checked; change(); });
  $("pointBox").addEventListener("toggle", renderPoints);
  $("distPer").addEventListener("change", () => { $("distPer").dataset.user = "1"; renderPoints(); });
  $("citySel").addEventListener("change", (e) => {
    const c = CITIES.find((x) => x[0] === e.target.value);
    if (c) { PT.city = c[0]; PT.lat = c[1]; PT.lon = c[2]; $("latIn").value = c[1]; $("lonIn").value = c[2]; } else PT.city = "";
    renderPoints();
  });
  for (const id of ["latIn", "lonIn"]) $(id).addEventListener("change", () => {
    const a = Number($("latIn").value), b = Number($("lonIn").value);
    if (Number.isFinite(a) && Number.isFinite(b)) { PT.lat = a; PT.lon = b; PT.city = ""; $("citySel").value = ""; renderPoints(); }
  });
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
  ensoLine();
}

// エルニーニョの状態を1行で表示する（enso.json があるときだけ）。強いエルニーニョ時は、技能の傾向を添える。
async function ensoLine() {
  try {
    const d = await (await fetch("enso.json", { cache: "no-store" })).json();
    const s = d.state, box = $("ensoLine");
    let t = `エルニーニョ監視: ${s.kind}（${s.text}）`;
    if (s.trailing5 >= 1.5) t += "　強いエルニーニョ年は、過去の検証で長期予報の技能が上がる傾向がありました（標本は2年）。";
    box.replaceChildren(document.createTextNode(t + " "));
    const a = document.createElement("a");
    a.href = "enso.html";
    a.textContent = "詳しく見る";
    box.appendChild(a);
    box.hidden = false;
  } catch (e) { /* enso.json が無ければ何も出さない */ }
}
main();
