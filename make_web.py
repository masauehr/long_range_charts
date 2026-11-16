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
]
REGIONS = {"asia": "東アジア", "global": "全球"}
RE_CFS = re.compile(r"^cfsv2_(\d{8})_([a-z0-9]+)_([A-Za-z0-9]+)_(asia|global)(_lag)?\.png$")
RE_CLIM = re.compile(r"^clim_(cfs_week|cfs_month|cps4)_(\d{8})_([a-z0-9]+)_([A-Za-z0-9\-]+)_(asia|global)\.png$")      # 気候値の図（climview.py）
RE_PT = re.compile(r"^pt_(cfs_week|cfs_month|cps4)_(\d{8})\.json$")                                                    # 地点の数値（climview.py）
RE_CPS = re.compile(r"^cps4_(\d{8})_([a-z0-9]+)_([A-Za-z0-9\-]+)_(asia|global)\.png$")


def init_text(init, cps=False):
    d = dt.datetime.strptime(init, "%Y%m%d")
    return f"{d.year}年{d.month}月{d.day}日" + ("基準" if cps else " 00Z 初期値")


def period_text(series, init, period):
    if series == "cps4":
        return cps4.make_periods(int(init[4:6]))[period][1]
    if period.startswith("W"):
        return weekly.span_label(init, weekly.WEEKS[period])
    return charts.period_label(init, charts.PERIODS[period])


def classify(fn):
    """ファイル名 → (系列, 初期日, 変数, 期間, 領域) または None。"""
    m = RE_CPS.match(fn)
    if m:
        return ("cps4", m.group(1), m.group(2), m.group(3), m.group(4))
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
        it = series[sid]["inits"].setdefault(init, {"init": init, "label": init_text(init, sid == "cps4"),
                                                    "vars": {}, "periods": {}, "files": {}})
        it["vars"][var] = charts.VARS[var]["label"]
        it["periods"][period] = period_text(sid, init, period)
        it["files"][f"{var}|{period}|{region}"] = fn
    climf, pts = {}, {}
    for fn in sorted(os.listdir(out_dir)):                    # 気候値の図と地点の数値（ラグ版は4メンバー版の気候値の図を使う）
        m = RE_CLIM.match(fn)
        if m:
            sid, init, var, period, region = m.groups()
            climf.setdefault((sid, init), {})[f"{var}|{period}|{region}"] = fn
        m = RE_PT.match(fn)
        if m:
            pts[(m.group(1), m.group(2))] = fn
    for sid in series:
        src = "cfs_week" if sid == "cfs_week_lag" else sid
        for init, it in series[sid]["inits"].items():
            if (src, init) in climf:
                it["clim_files"] = climf[(src, init)]
            if sid != "cfs_week_lag" and (sid, init) in pts:
                it["points"] = pts[(sid, init)]
    out = []
    for sid, _, _ in SERIES:
        s = series[sid]
        s["inits"] = [s["inits"][k] for k in sorted(s["inits"], reverse=True)]
        if s["inits"]:
            out.append(s)
    return {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "regions": REGIONS, "series": out}


def main():
    m = build()
    os.makedirs(WEB, exist_ok=True)
    path = os.path.join(WEB, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    guide = os.path.join(clim.ROOT, "GUIDE.md")
    if os.path.exists(guide):                               # 初心者向けガイド（GUIDE.md）を画面用の guide.html にする
        with open(os.path.join(WEB, "guide.html"), "w", encoding="utf-8") as f:
            f.write(md2html.convert(open(guide, encoding="utf-8").read(), title="長期予報の図 かんたんガイド"))
    n = sum(len(i["files"]) for s in m["series"] for i in s["inits"])
    print(f"manifest: {n}枚・系列{[s['id'] for s in m['series']]} → {os.path.relpath(path, clim.ROOT)}")


if __name__ == "__main__":
    main()
