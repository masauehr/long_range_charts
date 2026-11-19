"""閲覧画面（web/）用の manifest.json を、output/ の図のファイル名から作る。

ファイル名の形式（charts.py / weekly.py / cps4.py の出力）:
  cfsv2_{初期日}_{変数}_{期間}_{領域}.png        CFS 月平均（期間 M1〜M4・Q1）または 週平均（W1〜W4）
  cfsv2_{初期日}_{変数}_{期間}_{領域}_lag.png    CFS 週平均のラグアンサンブル版
  cps4_{基準日}_{変数}_{期間}_{領域}.png         JMA CPS4（C3S 経由。期間 L1〜L4・L2-4）
画面は web/index.html。図は ../output/ を相対参照する（output/ は git 除外）。公開は Phase 5・NOTICE.md の確認後。

使い方: python make_web.py
"""
import datetime as dt
import json
import os
import re

import cps4
import charts
import clim
import md2html
import weekly

OUT = charts.OUT
WEB = os.path.join(clim.ROOT, "web")

# 系列の定義（表示順）
SERIES = [
    ("cfs_week", "CFSv2 週平均（4メンバー）",
     "NOAA CFSv2（00Z・4メンバー）の週平均。気候値は CFSv2 運用予報 2019–2025 の約7年。確率は観測（再解析）との照合に基づき縮小済み。"
     "週3〜4の東アジアは過去の照合で技能が乏しい。"),
    ("cfs_week_lag", "CFSv2 週平均（ラグ18メンバー）",
     "上と同じ週平均に、前2日の各サイクルを加えて18メンバーにしたもの（初期日のずれは補正）。確率の刻みが細かい。"
     "週1・週2は古い初期値の分だけ精度が落ちうる。観測との照合は4メンバー版のみ。"),
    ("cfs_month", "CFSv2 月平均（暦月・4メンバー）",
     "NOAA CFSv2（00Z・4メンバー）の暦月平均。初月は初期日以降の部分月。気候値は CFSv2 運用予報 2019–2025 の同月初期日（約7年）。"
     "東アジアの12月以降は過去の照合で技能が乏しい。"),
    ("cps4", "JMA CPS4 月平均（C3S経由・155メンバー）",
     "気象庁の季節予報システム CPS4（Copernicus C3S 経由）。基準日は11/1（CFS の11/12 より古い）。気候値はハインドキャスト 1993–2020"
     "（28年×10メンバー）。確率は観測との照合（10メンバー）に基づき縮小済み。東アジアの12月以降は過去の照合で技能が乏しい"
     "（強い El Niño 年は上がるが標本は2年）。気象庁の公式の長期予報（高い/平年並/低い）とは定義が異なる。"),
    ("ecmwf", "ECMWF SEAS5 月平均（C3S経由・51メンバー）",
     "ECMWF の季節予報 SEAS5（Copernicus C3S 経由・system 51）。基準日は月初（11/1）。気候値はハインドキャスト 1993–2016"
     "（24年×25メンバー。予報は51メンバーで数が違う）。確率は観測との照合（24年・25メンバー）に基づき縮小済み。東アジアの12月以降は過去の照合で技能が乏しい。格子は1°。"
     "2m気温・降水・500hPa高度・海面水温・力学診断（流線関数・速度ポテンシャル・OLR）。気象庁の公式の長期予報（高い/平年並/低い）とは定義が異なる。"),
]
DOCS = [("GUIDE.md", "guide.html", "長期予報の図 かんたんガイド", [("manual.html", "操作マニュアル")]),
        ("MANUAL.md", "manual.html", "長期予報の図 操作マニュアル", [("guide.html", "使い方ガイド")])]
REGIONS = {"asia": "東アジア", "global": "全球", "jma": "気象庁形式（60°S–60°N）"}
RE_CFS = re.compile(r"^cfsv2_(\d{8})_([a-z0-9]+)_([A-Za-z0-9]+)_(asia|global|jma)(_lag)?\.png$")
RE_CLIM = re.compile(r"^clim_(cfs_week|cfs_month|cps4|ecmwf)_(\d{8})_([a-z0-9]+)_([A-Za-z0-9\-]+)_(asia|global)\.png$")      # 気候値の図（climview.py）
RE_PT = re.compile(r"^pt_(cfs_week|cfs_month|cps4|ecmwf)_(\d{8})\.json$")                                                    # 地点の数値（climview.py）
RE_DIST = re.compile(r"^dist_(cfs_week|cfs_month|cps4|ecmwf)_(\d{8})\.json$")                                                  # 地点の分布図のデータ（distview.py）
RE_TELE = re.compile(r"^telecon_(cfs_week|cfs_month|cps4)_(\d{8})\.json$")                                              # テレコネクション指数（telecon.py）
RE_CPS = re.compile(r"^(cps4|ecmwf)_(\d{8})_([a-z0-9]+)_([A-Za-z0-9\-]+)_(asia|global|jma)\.png$")      # JMA CPS4・ECMWF SEAS5（どちらも C3S 経由・期間 L1〜L4・L2-4）


def init_text(init, cps=False):
    d = dt.datetime.strptime(init, "%Y%m%d")
    return f"{d.year}年{d.month}月{d.day}日" + ("基準" if cps else " 00Z 初期値")


def period_text(series, init, period):
    if series in ("cps4", "ecmwf"):
        return cps4.make_periods(int(init[4:6]))[period][1]
    if period.startswith("W"):
        return weekly.span_label(init, weekly.WEEKS[period])
    return charts.period_label(init, charts.PERIODS[period])


def classify(fn):
    """ファイル名 → (系列, 初期日, 変数, 期間, 領域) または None。"""
    m = RE_CPS.match(fn)
    if m:
        return (m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
    m = RE_CFS.match(fn)
    if m:
        init, var, period, region, lag = m.groups()
        if period.startswith("W"):
            return ("cfs_week_lag" if lag else "cfs_week", init, var, period, region)
        if not lag:
            return ("cfs_month", init, var, period, region)
    return None


def build(out_dir=OUT):
    series = {sid: {"id": sid, "label": lab, "note": note, "inits": {}} for sid, lab, note in SERIES}
    for fn in sorted(os.listdir(out_dir)):
        c = classify(fn)
        if not c:
            continue
        sid, init, var, period, region = c
        if var not in charts.VARS:
            continue
        it = series[sid]["inits"].setdefault(init, {"init": init, "label": init_text(init, sid in ("cps4", "ecmwf")),
                                                    "vars": {}, "periods": {}, "files": {}})
        it["vars"][var] = charts.VARS[var]["label"]
        it["periods"][period] = period_text(sid, init, period)
        it["files"][f"{var}|{period}|{region}"] = fn
    climf, pts, dists, teles = {}, {}, {}, {}
    for fn in sorted(os.listdir(out_dir)):                    # 気候値の図と地点の数値（ラグ版は4メンバー版の気候値の図を使う）
        m = RE_CLIM.match(fn)
        if m:
            sid, init, var, period, region = m.groups()
            climf.setdefault((sid, init), {})[f"{var}|{period}|{region}"] = fn
        m = RE_PT.match(fn)
        if m:
            pts[(m.group(1), m.group(2))] = fn
        m = RE_DIST.match(fn)
        if m:
            dists[(m.group(1), m.group(2))] = fn
        m = RE_TELE.match(fn)
        if m:
            teles[(m.group(1), m.group(2))] = fn
    for sid in series:
        src = "cfs_week" if sid == "cfs_week_lag" else sid
        for init, it in series[sid]["inits"].items():
            if (src, init) in climf:
                it["clim_files"] = climf[(src, init)]
            if sid != "cfs_week_lag" and (sid, init) in pts:
                it["points"] = pts[(sid, init)]
            if sid != "cfs_week_lag" and (sid, init) in dists:
                it["dist"] = dists[(sid, init)]
            if sid != "cfs_week_lag" and (sid, init) in teles:
                it["telecon"] = teles[(sid, init)]
    out = []
    for sid, _, _ in SERIES:
        s = series[sid]
        s["inits"] = [s["inits"][k] for k in sorted(s["inits"], reverse=True)]
        if s["inits"]:
            out.append(s)
    return {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "regions": REGIONS, "series": out}


def write_jma_page():
    """web/jma.html を web/index.html から作る（標準表示と同じ画面・同じ操作で、気象庁形式の図だけを見るページ）。"""
    src = os.path.join(WEB, "index.html")
    t = open(src, encoding="utf-8").read()
    t = t.replace("<title>長期予報用 統計図ビューア</title>", "<title>気象庁形式の図（予報）</title>", 1)
    t = t.replace("<body>", '<body data-page="jma">', 1)
    t = t.replace("<h1>長期予報用 統計図ビューア</h1>", "<h1>気象庁形式の図（予報）</h1>", 1)
    t = t.replace("</head>", "<style>#regionBtns, #modeBtns, .hrow .chk, #pointBox, #jmaNote ~ #pointBox { display: none !important; }</style>\n</head>", 1)
    t = t.replace('<a href="jma.html" class="jma-link">気象庁形式の図</a>', '<a href="index.html" class="std-link">標準表示</a>', 1)
    t = t.replace('<p class="banner" role="note">', '<p id="jmaNote" class="banner" role="note"><strong>気象庁の「速報」と同じ表示形式</strong>で描いた予報です（気象庁の図は実況の平年差・こちらは<strong>予報</strong>で、偏差の基準はモデル自身の気候値）。操作は標準表示と同じです。　', 1)
    t = t.replace('<script src="app.js"></script>', '<script src="app.js"></script>\n<script src="jma.js"></script>', 1)   # コマ送り／一覧の切替
    with open(os.path.join(WEB, "jma.html"), "w", encoding="utf-8") as f:
        f.write(t)


def main():
    m = build()
    os.makedirs(WEB, exist_ok=True)
    path = os.path.join(WEB, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    write_jma_page()
    for md, out_name, title, links in DOCS:                 # 初心者向けガイド（GUIDE.md）・操作マニュアル（MANUAL.md）を画面用の html にする
        src = os.path.join(clim.ROOT, md)
        if os.path.exists(src):
            with open(os.path.join(WEB, out_name), "w", encoding="utf-8") as f:
                f.write(md2html.convert(open(src, encoding="utf-8").read(), title=title, links=links))
    n = sum(len(i["files"]) for s in m["series"] for i in s["inits"])
    print(f"manifest: {n}枚・系列{[s['id'] for s in m['series']]} → {os.path.relpath(path, clim.ROOT)}")


if __name__ == "__main__":
    main()
