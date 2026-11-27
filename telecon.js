// テレコネクション指数（PNA・WP・EU）の予報ページ。manifest の telecon（output/telecon_*.json）を読んで表と棒で表示する。
"use strict";
let M = null, IMG_DIR = "../output/";
const S = { series: null, init: null };
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const PERIOD_ORDER = ["W1", "W2", "W3", "W4", "M1", "M2", "M3", "M4", "Q1", "L1", "L2", "L3", "L4", "L2-4"];
const DATA = {};

const hasTele = (it) => !!it.telecon;
const seriesList = () => M.series.filter((s) => s.inits.some(hasTele));
const seriesOf = () => seriesList().find((s) => s.id === S.series) || seriesList()[0];
const initsOf = () => seriesOf().inits.filter(hasTele);
const initOf = () => initsOf().find((i) => i.init === S.init) || initsOf()[0];
function option(sel, items, cur) { sel.replaceChildren(...items.map(([v, t]) => { const o = el("option", null, t); o.value = v; o.selected = v === cur; return o; })); }

function zbar(z, members, sd) {
  const box = el("div", "zbar");
  box.append(el("div", "band"), el("div", "mid"));
  const clamp = (v) => Math.max(-3, Math.min(3, v));
  const v = el("div", "val");
  const w = (Math.abs(clamp(z)) / 3) * 50;
  v.style.width = w + "%";
  v.style.left = (z >= 0 ? 50 : 50 - w) + "%";
  v.style.background = z >= 0 ? "rgba(214,60,50,0.75)" : "rgba(60,110,190,0.75)";
  box.appendChild(v);
  if (sd > 0) for (const m of members) { const d = el("div", "dot"); d.style.left = `calc(${50 + (clamp(m / sd) / 3) * 50}% - 2px)`; box.appendChild(d); }
  return box;
}

async function render() {
  const it = initOf();
  option($("seriesSel"), seriesList().map((s) => [s.id, s.label]), S.series);
  option($("initSel"), initsOf().map((i) => [i.init, i.label]), S.init);
  $("updated").textContent = `一覧の更新: ${M.generated}`;
  if (!DATA[it.telecon]) {
    try { DATA[it.telecon] = await (await fetch(IMG_DIR + it.telecon, { cache: "no-store" })).json(); } catch (e) { $("tables").textContent = "指数のデータを読めません。"; return; }
  }
  const d = DATA[it.telecon], box = $("tables");
  box.replaceChildren();
  for (const [k, v] of Object.entries(d.indices)) {
    const sec = el("section", "card");
    sec.appendChild(el("h2", null, v.label));
    sec.appendChild(el("p", "muted", `${v.note}　（点: ${v.points.map((p) => `${Math.abs(p.lat)}°${p.lat >= 0 ? "N" : "S"}・${Math.abs(p.lon)}°${p.lon >= 0 ? "E" : "W"}×${p.w > 0 ? "+" : ""}${p.w}`).join(" / ")}）`));
    const t = el("table"), head = el("tr");
    for (const h of ["期間", "予報(gpm)", "標準化値", "標準化値の棒（点=各メンバー）", "気候値の標準偏差(gpm)", "位置(%)"]) head.appendChild(el("th", null, h));
    t.appendChild(el("thead")).appendChild(head);
    const body = el("tbody");
    const ps = Object.keys(v.periods).sort((a, b) => PERIOD_ORDER.indexOf(a) - PERIOD_ORDER.indexOf(b));
    for (const p of ps) {
      const r = v.periods[p], tr = el("tr");
      const c1 = el("td", "lab", `${p}　${r.label}`);
      const c2 = el("td", r.fc >= 0 ? "pos" : "neg", (r.fc >= 0 ? "+" : "") + r.fc);
      const c3 = el("td", r.z >= 0 ? "pos" : "neg", r.z == null ? "—" : (r.z >= 0 ? "+" : "") + r.z.toFixed(2));
      const c4 = el("td"); c4.appendChild(zbar(r.z || 0, r.members, r.sd));
      tr.append(c1, c2, c3, c4, el("td", null, String(r.sd)), el("td", null, String(r.pct)));
      body.appendChild(tr);
    }
    t.appendChild(body);
    sec.appendChild(t);
    box.appendChild(sec);
  }
  try { history.replaceState(null, "", `#s=${S.series}&i=${S.init}`); } catch (e) { /* 無視 */ }
}

async function main() {
  try { M = await (await fetch("manifest.json", { cache: "no-store" })).json(); } catch (e) { $("tables").textContent = "manifest.json を読めません。"; return; }
  if (M.imgdir) IMG_DIR = M.imgdir;
  if (!M.series.some((x) => x.id === "cps4")) document.querySelectorAll(".c3s").forEach((e) => e.remove());
  if (!seriesList().length) { $("tables").textContent = "指数のデータがまだありません（python telecon.py を実行してください）。"; return; }
  const p = new URLSearchParams(location.hash.slice(1));
  S.series = p.get("s") || seriesList()[0].id;
  S.init = p.get("i");
  $("seriesSel").addEventListener("change", (e) => { S.series = e.target.value; S.init = null; render(); });
  $("initSel").addEventListener("change", (e) => { S.init = e.target.value; render(); });
  S.series = seriesOf().id; S.init = initOf().init;
  render();
}
main();
