// エルニーニョ監視ページ。enso.json（enso.py が作る）を読み、状態・観測の図・CPS4 の予測の図と表を表示する。
// 気象庁の公式の見通し（jma）は、ローカルの enso.json にだけ入る（公開版には載せない）。
"use strict";
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
let D = null;
let IMG_DIR = "../output/";

function stateCard() {
  const s = D.state, c = $("stateCard");
  c.replaceChildren(el("h2", null, "現在の状態（観測からの目安）"));
  const big = el("p", "bigstate", s.kind);
  c.append(big, el("p", null, s.text), el("p", "muted", "NOAA ERSSTv5 による目安で、気象庁の公式判定ではありません。"));
}

function jmaCard() {
  const j = D.jma, c = $("jmaCard");
  if (!j) return;
  c.hidden = false;
  c.replaceChildren(el("h2", null, "気象庁の公式の見通し（ローカル表示のみ）"), el("p", "muted", "↓これは気象庁が発表した内容の要約です。下の「観測」「予測」の図は気象庁の図ではなく、このサイトが NOAA・JMA/MRI-CPS4 のデータから計算したものです。"));
  const ul = el("ul");
  for (const t of [j.status, j.values, j.outlook]) if (t) ul.appendChild(el("li", null, t));
  const src = el("p", "muted");
  const a = el("a", null, j.source);
  a.href = j.detail_url || j.url;
  src.append("出典: ", a, `（発表 ${j.issued}・次回 ${j.next_issue || "—"}・取得 ${j.retrieved}）`);
  c.append(ul, src, el("p", "muted", j.note || ""));
}

function table(title, k, f) {
  const r = f[k];
  const box = el("div");
  box.appendChild(el("h3", null, title));
  const t = el("table");
  const head = el("tr");
  for (const h of ["月", "平均偏差(℃)", "10〜90%の範囲(℃)", "エルニーニョ側", "ラニーニャ側", "過去28年のACC"]) head.appendChild(el("th", null, h));
  t.appendChild(el("thead")).appendChild(head);
  const body = el("tbody");
  r.months.forEach((m, i) => {
    const tr = el("tr");
    const lo = r.p10[i], hi = r.p90[i];
    for (const v of [m, (r.mean[i] >= 0 ? "+" : "") + r.mean[i].toFixed(1), `${lo.toFixed(1)} 〜 ${hi.toFixed(1)}`,
                     `${r.p_el[i]}%`, `${r.p_la[i]}%`, r.acc[i] == null ? "—" : r.acc[i].toFixed(2)]) tr.appendChild(el("td", null, v));
    body.appendChild(tr);
  });
  t.appendChild(body);
  box.appendChild(t);
  return box;
}

function forecast() {
  const sel = $("fcSel");
  if (!sel) return;                                   // 公開版には予測の欄が無い（JMA/MRI-CPS4 はローカル版のみ）
  const f = D.forecasts.find((x) => x.init === sel.value) || D.forecasts[0];
  if (!f) { $("fcImg").hidden = true; $("fcTables").textContent = "予測の図がまだありません。"; return; }
  $("fcImg").hidden = false;
  $("fcImg").src = IMG_DIR + f.image;
  const box = $("fcTables");
  box.replaceChildren(table("NINO.3（気象庁の指標）", "nino3", f), table("NINO.3.4（NOAAの従来のONI方式）", "nino34", f),
                      el("p", "muted", `予報 ${f.n_members} メンバー。確率は偏差が±0.5℃を超えたメンバーの割合（補正前）。`));
  try { history.replaceState(null, "", "#i=" + f.init); } catch (e) { /* 無視 */ }
}

async function main() {
  try { D = await (await fetch("enso.json", { cache: "no-store" })).json(); }
  catch (e) { document.querySelector("main").textContent = "enso.json を読めません。python enso.py を実行してください。"; return; }
  if (D.imgdir) IMG_DIR = D.imgdir;
  $("updated").textContent = `更新: ${D.generated}`;
  stateCard();
  jmaCard();
  $("obsImg").src = IMG_DIR + D.obs_image;
  $("obsNote").textContent = D.note;
  const sel = $("fcSel");
  if (!sel) return;
  sel.replaceChildren(...D.forecasts.map((f) => { const o = el("option", null, f.label); o.value = f.init; return o; }));
  const want = new URLSearchParams(location.hash.slice(1)).get("i");
  if (want && D.forecasts.some((f) => f.init === want)) sel.value = want;
  sel.addEventListener("change", forecast);
  forecast();
}
main();
