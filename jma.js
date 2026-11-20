// 気象庁形式のページ（jma.html）に、「コマ送り（標準表示と同じ）」と「一覧（変数を縦に並べる）」の切替を足す。
// app.js が作る画面（M・S・render・change・periodsOf・IMG_DIR などの共通の名前）を使い、一覧のときだけ、変数ごとの図を縦に並べて表示する。
(function () {
  "use strict";
  const LIST_VARS = [["psi200", "流線関数（200hPa）"], ["psi850", "流線関数（850hPa）"], ["chi200", "速度ポテンシャル（200hPa）・OLR・流線関数"], ["olr", "OLR"], ["sst", "海面水温"], ["pot5", "海面付近(5m)の水温"]];
  const KEY = "jmaViewMode";
  let mode = "frame";
  try { mode = localStorage.getItem(KEY) === "list" ? "list" : "frame"; } catch (e) { /* 使えないときは既定 */ }
  let size = "100";

  const $$ = (id) => document.getElementById(id);
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const FRAME_IDS = ["varTabs", "controls", "timeInfo", "panels"];
  const frameBlocks = () => [...FRAME_IDS.map($$), ...document.querySelectorAll("main section")].filter((e) => e && e.id !== "jmaList" && !e.classList.contains("about"));

  // ---- 切替ボタンと一覧の入れ物
  const bar = mk("div", "seg");
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", "表示の形式");
  const hrow = document.querySelector("header .hrow");
  hrow.insertBefore(bar, hrow.firstChild);
  const list = mk("div", "jmalist");
  list.id = "jmaList";
  list.hidden = true;
  document.querySelector("main").insertBefore(list, document.querySelector("main").firstChild);

  function setMode(m) {
    mode = m;
    try { localStorage.setItem(KEY, m); } catch (e) { /* 無視 */ }
    apply();
  }
  function drawBar() {
    bar.replaceChildren(...[["frame", "コマ送り（標準表示と同じ）"], ["list", "一覧（変数を縦に並べる）"]].map(([v, t]) => {
      const b = mk("button", null, t);
      b.type = "button";
      b.setAttribute("aria-pressed", String(v === mode));
      b.addEventListener("click", () => setMode(v));
      return b;
    }));
  }
  function apply() {
    drawBar();
    const listMode = mode === "list";
    for (const e of frameBlocks()) e.hidden = listMode;
    list.hidden = !listMode;
    if (listMode && typeof M !== "undefined" && M) renderList();
  }

  // ---- 一覧（変数ごとの図を縦に並べる）
  function renderList() {
    const L = S.L, it = initOf(L), ps = periodsOf(L);
    list.replaceChildren();
    const head = mk("div", "hrow");
    const sel = mk("select");
    sel.setAttribute("aria-label", "期間");
    for (const p of ps) { const o = mk("option", null, `${p}　${it.periods[p]}`); o.value = p; o.selected = p === L.period; sel.appendChild(o); }
    sel.addEventListener("change", () => { S.L.period = sel.value; change(); });
    const prev = mk("button", null, "|◀"), next = mk("button", null, "▶|");
    prev.type = next.type = "button";
    prev.title = "1コマ戻る (←)"; next.title = "1コマ進む (→)";
    const idx = ps.indexOf(L.period);
    prev.disabled = idx <= 0; next.disabled = idx >= ps.length - 1;
    prev.addEventListener("click", () => step(-1));
    next.addEventListener("click", () => step(1));
    const sz = mk("select");
    sz.setAttribute("aria-label", "図の大きさ");
    for (const [v, t] of [["100", "幅いっぱい"], ["80", "80%"], ["60", "60%"]]) { const o = mk("option", null, t); o.value = v; o.selected = v === size; sz.appendChild(o); }
    sz.addEventListener("change", () => { size = sz.value; renderList(); });
    const lab = mk("span", "lab", "期間");
    head.append(lab, sel, prev, next, mk("span", "lab", "大きさ"), sz);
    list.appendChild(head);
    let n = 0;
    for (const [v, label] of LIST_VARS) {
      const f = it.files[`${v}|${L.period}|jma`];
      if (!f) continue;
      n += 1;
      const fig = mk("figure", "jmafig");
      fig.appendChild(mk("h2", null, `図${n}　${label}・平年差（予報: ${it.periods[L.period]}）`));
      const img = mk("img");
      img.src = IMG_DIR + f;
      img.alt = `${label} ${it.periods[L.period]}`;
      img.style.width = (v === "chi200" ? Math.min(Number(size), 70) : size) + "%";
      img.addEventListener("error", () => img.replaceWith(mk("div", "msg", `画像を読み込めませんでした: ${f}`)));
      fig.appendChild(img);
      list.appendChild(fig);
    }
    if (!n) list.appendChild(mk("div", "msg", "この期間の気象庁形式の図はありません。"));
  }

  // ---- app.js の描画に、一覧の更新をつなぐ（系列・初期値・期間が変わるたびに一覧も更新する）
  const base = window.render;
  window.render = function () {
    base();
    const listMode = mode === "list";
    for (const e of frameBlocks()) e.hidden = listMode;
    list.hidden = !listMode;
    if (listMode) renderList();
  };
  drawBar();
  apply();
})();
