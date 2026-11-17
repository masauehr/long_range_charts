// 気象庁形式の図（予報）を、変数を縦に並べて見るページ。気象庁の「速報」の図に合わせた形式（地域キー jma）の図を、manifest から集める。
"use strict";

const VARS = [["psi200", "流線関数（200hPa）"], ["psi850", "流線関数（850hPa）"], ["chi200", "速度ポテンシャル（200hPa）・OLR"], ["olr", "OLR"], ["sst", "海面水温"], ["pot5", "海面付近(5m)の水温"]];
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L2-4"];
let M = null;
let IMG_DIR = "../output/";
const S = { series: null, init: null, period: null, size: "100" };
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const sortBy = (arr, order) => [...arr].sort((a, b) => ((order.indexOf(a) + 99) % 99) - ((order.indexOf(b) + 99) % 99));

const hasJma = (it) => Object.keys(it.files).some((k) => k.endsWith("|jma"));
const seriesList = () => M.series.filter((s) => s.inits.some(hasJma));
const seriesOf = () => seriesList().find((s) => s.id === S.series) || seriesList()[0];
const initsOf = () => seriesOf().inits.filter(hasJma);
const initOf = () => initsOf().find((i) => i.init === S.init) || initsOf()[0];
const periodsOf = () => sortBy([...new Set(Object.keys(initOf().files).filter((k) => k.endsWith("|jma")).map((k) => k.split("|")[1]))], PERIOD_ORDER);

function option(sel, items, cur) {
  sel.replaceChildren(...items.map(([v, t]) => { const o = el("option", null, t); o.value = v; o.selected = v === cur; return o; }));
}
function fix() {
  S.series = seriesOf().id;
  S.init = initOf().init;
  if (!periodsOf().includes(S.period)) S.period = periodsOf()[0];
}
function render() {
  fix();
  const it = initOf(), ps = periodsOf();
  option($("seriesSel"), seriesList().map((s) => [s.id, s.label]), S.series);
  option($("initSel"), initsOf().map((i) => [i.init, i.label]), S.init);
  option($("perSel"), ps.map((p) => [p, `${p}　${it.periods[p]}`]), S.period);
  $("sizeSel").value = S.size;
  $("updated").textContent = `一覧の更新: ${M.generated}`;
  const box = $("figs");
  box.replaceChildren();
  let n = 0;
  for (const [v, label] of VARS) {
    const f = it.files[`${v}|${S.period}|jma`];
    if (!f) continue;
    n += 1;
    const fig = el("figure", "jmafig");
    fig.appendChild(el("h2", null, `図${n}　${label}・平年差（予報: ${it.periods[S.period]}）`));
    const img = el("img");
    img.src = IMG_DIR + f;
    img.alt = `${label} ${it.periods[S.period]}`;
    img.style.width = (v === "chi200" ? Math.min(Number(S.size), 70) : S.size) + "%";
    img.addEventListener("error", () => img.replaceWith(el("div", "msg", `画像を読み込めませんでした: ${f}`)));
    fig.appendChild(img);
    box.appendChild(fig);
  }
  if (!n) box.appendChild(el("div", "msg", "この期間の気象庁形式の図はありません。"));
  try { history.replaceState(null, "", `#s=${S.series}&i=${S.init}&p=${S.period}&z=${S.size}`); } catch (e) { /* 無視 */ }
}
function step(d) {
  const ps = periodsOf(), i = ps.indexOf(S.period) + d;
  if (i >= 0 && i < ps.length) { S.period = ps[i]; render(); }
}
async function main() {
  try { M = await (await fetch("manifest.json", { cache: "no-store" })).json(); }
  catch (e) { $("figs").textContent = "manifest.json を読めません。python make_web.py を実行してください。"; return; }
  if (M.imgdir) IMG_DIR = M.imgdir;
  if (!M.series.some((x) => x.id === "cps4")) document.querySelectorAll(".c3s").forEach((e) => e.remove());
  if (!seriesList().length) { $("figs").textContent = "気象庁形式の図がまだありません（python jma_style.py を実行してください）。"; return; }
  const p = new URLSearchParams(location.hash.slice(1));
  S.series = p.get("s") || seriesList()[0].id;
  S.init = p.get("i");
  S.period = p.get("p");
  S.size = ["100", "80", "60"].includes(p.get("z")) ? p.get("z") : "100";
  $("seriesSel").addEventListener("change", (e) => { S.series = e.target.value; S.init = null; S.period = null; render(); });
  $("initSel").addEventListener("change", (e) => { S.init = e.target.value; render(); });
  $("perSel").addEventListener("change", (e) => { S.period = e.target.value; render(); });
  $("sizeSel").addEventListener("change", (e) => { S.size = e.target.value; render(); });
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  document.addEventListener("keydown", (e) => {
    if (["SELECT", "INPUT"].includes(e.target.tagName)) return;
    if (e.key === "ArrowLeft") { step(-1); e.preventDefault(); } else if (e.key === "ArrowRight") { step(1); e.preventDefault(); }
  });
  render();
}
main();
