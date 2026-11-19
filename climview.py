"""気候値（平年）を画面で見られるようにする: ①気候値の図（気候値・下位1/3の境目・上位1/3の境目・境目の幅）②地点の数値表用のデータ。

入力（ほかのスクリプトが保存した統計。気候値は図を作るたびに計算していたものをここで見える形にする）:
  cfs_week : data/weekly_{初期日}.npz（weekly.py）   期間 W1〜W4
  cfs_month: data/monthly_{初期日}.npz（charts.py）   期間 M1〜M4・Q1
  cps4     : data/cps4_{基準日}_{変数}.npz（cps4.py） 期間 L1〜L4・L2-4
出力（output/）:
  clim_{系列}_{初期日}_{変数}_{期間}_{領域}.png   気候値の図（4枚組）
  pt_{系列}_{初期日}.json                        東アジア（北緯8〜62・東経95〜175）の 2.5° 格子の数値（気候値・境目・予報・偏差・確率）。画面の「地点の数値」が読む。
  ※ラグ18メンバー版は気候値が同じなので、4メンバー版（cfs_week）の気候値の図を使う。地点の数値は4メンバー版のみ。

使い方: python climview.py --series cfs_week cfs_month --init 20261116
        python climview.py --series cps4 --init 20261101
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

import charts
import clim
import cps4
import weekly
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.ticker import MaxNLocator

OUT = charts.OUT
BOX = (8, 62, 95, 175)                    # 地点の数値の範囲（東アジア）
CMAP = {"t2m": "RdYlBu_r", "prate": "YlGnBu", "z500": "RdYlBu_r", "sst": "RdYlBu_r", "pot5": "RdYlBu_r",
        "psi850": "RdYlBu_r", "psi200": "RdYlBu_r", "chi200": "PuOr_r", "olr": "YlGnBu_r"}
SERIES_LABEL = {"cfs_week": "CFSv2 週平均", "cfs_month": "CFSv2 月平均", "cps4": "JMA CPS4 月平均", "ecmwf": "ECMWF SEAS5 月平均"}
CPS4_CLIM_TEXT = "JMA/MRI-CPS4 のハインドキャスト 1993–2020年（28年×10メンバー）"
ECMWF_CLIM_TEXT = "ECMWF SEAS5 のハインドキャスト 1993–2016年（24年×25メンバー）"


# ------------------------------------------------------------------ 入力
def load_source(sid, init):
    """戻り値: (lat, lon, {期間: {"label":…, "alpha_key":…}}, {変数: {期間: dict(mean,t33,t67,anom,pu,pl)}}, 気候値の説明文, 出典の文)。"""
    if sid == "cfs_week":
        names = list(weekly.WEEKS)
        data = {}
        for fname in (f"weekly_{init}.npz", f"weekly_dyn_{init}.npz"):          # 通常の変数と、力学診断（weekly_dyn.py）
            pth = os.path.join(clim.DATA, fname)
            if not os.path.exists(pth):
                continue
            zz = np.load(pth)
            for vi, v in enumerate(str(x) for x in zz["vars"]):
                data[v] = {n: dict(mean=zz[f"{n}_mean"][vi], t33=zz[f"{n}_t33"][vi], t67=zz[f"{n}_t67"][vi],
                                   anom=zz[f"{n}_anom"][vi], pu=zz[f"{n}_p_upper"][vi], pl=zz[f"{n}_p_lower"][vi]) for n in names}
        z = np.load(os.path.join(clim.DATA, f"weekly_{init}.npz"))
        labels = {n: weekly.span_label(init, weekly.WEEKS[n]) for n in names}
        return z["lat"], z["lon"], labels, data, weekly.CLIM_TEXT_DAILY, "NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。"
    if sid == "cfs_month":
        names = list(charts.PERIODS)
        data = {}
        for fname in (f"monthly_{init}.npz", f"monthly_dyn_{init}.npz"):      # 通常の変数と、力学診断（dyn.py）
            pth = os.path.join(clim.DATA, fname)
            if not os.path.exists(pth):
                continue
            z = np.load(pth)
            for vi, v in enumerate(str(x) for x in z["vars"]):
                data[v] = {n: dict(mean=z[f"{n}_mean"][vi], t33=z[f"{n}_t33"][vi], t67=z[f"{n}_t67"][vi],
                                   anom=z[f"{n}_anom"][vi], pu=z[f"{n}_p_upper"][vi], pl=z[f"{n}_p_lower"][vi]) for n in names}
        z = np.load(os.path.join(clim.DATA, f"monthly_{init}.npz"))
        labels = {n: charts.period_label(init, charts.PERIODS[n]) for n in names}
        return z["lat"], z["lon"], labels, data, charts.CLIM_TEXT_MONTHLY, "NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。"
    if sid == "cps4":
        month = int(init[4:6])
        periods = cps4.make_periods(month)
        names = ["L1", "L2", "L3", "L4", "L2-4"]
        data, lat, lon = {}, None, None
        for short in ("t2m", "prate", "z500", "sst", "psi850", "psi200", "chi200", "olr"):
            p = os.path.join(clim.DATA, f"cps4_{init}_{short}.npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            data[short] = {n: dict(mean=z[f"{n}_mean"], t33=z[f"{n}_t33"], t67=z[f"{n}_t67"], anom=z[f"{n}_anom"],
                                   pu=z[f"{n}_p_upper"], pl=z[f"{n}_p_lower"]) for n in names}
        labels = {n: periods[n][1] for n in names}
        return lat, lon, labels, data, CPS4_CLIM_TEXT, "JMA/MRI-CPS4（Copernicus C3S 経由）を加工して作成。気象庁・C3Sの推奨を示すものではない。"
    if sid == "ecmwf":                                     # ECMWF SEAS5（C3S・ローカルのみ）。ecmwf_seas5.py の npz。期間は CPS4 と同じ
        periods = cps4.make_periods(int(init[4:6]))
        names = ["L1", "L2", "L3", "L4", "L2-4"]
        data, lat, lon = {}, None, None
        for short in ("t2m", "prate", "z500", "sst"):
            p = os.path.join(clim.DATA, f"ecmwf_{init}_{short}.npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            data[short] = {n: dict(mean=z[f"{n}_mean"], t33=z[f"{n}_t33"], t67=z[f"{n}_t67"], anom=z[f"{n}_anom"],
                                   pu=z[f"{n}_p_upper"], pl=z[f"{n}_p_lower"]) for n in names}
        labels = {n: periods[n][1] for n in names}
        return lat, lon, labels, data, ECMWF_CLIM_TEXT, "ECMWF SEAS5（Copernicus C3S 経由）を加工して作成。ECMWF・C3Sの推奨を示すものではない。"
    raise ValueError(sid)


# ------------------------------------------------------------------ 図
def _levels(fields, n=12):
    v = np.concatenate([f[np.isfinite(f)].ravel() for f in fields])
    lo, hi = np.percentile(v, [2, 98])
    lv = MaxNLocator(nbins=n, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
    return lv


def _cmap(name, lv, extend=True):
    cm = plt.get_cmap(name)
    n = len(lv) + (1 if extend else -1)
    cols = [cm(x) for x in np.linspace(0.03, 0.97, n)]
    return ListedColormap(cols), BoundaryNorm(lv, len(cols))


def render_clim(var, region, d, lat, lon, *, sid, init, label, clim_text, source_text, out_path):
    v = charts.VARS[var]
    rg = charts.REGIONS[region]
    fig = plt.figure(figsize=(rg["fig"][0] + 1, rg["fig"][1]), dpi=100)
    y, h = rg["rect_y"]
    w, gap = 0.232, 0.012
    rects = [[0.01 + i * (w + gap), y, w, h] for i in range(4)]
    lv_main = _levels([d["mean"]], 16)
    lo_d, hi_d = d["t33"] - d["mean"], d["t67"] - d["mean"]           # 境目は「平年との差」で見せる（絶対値だと気候値の図とほぼ同じ見た目になるため）
    m = float(np.nanpercentile(np.abs(np.concatenate([lo_d[np.isfinite(lo_d)], hi_d[np.isfinite(hi_d)]])), 98))
    ll = MaxNLocator(nbins=8, steps=[1, 2, 2.5, 5, 10]).tick_values(-m, m)
    lv_diff = np.unique(np.concatenate([-ll[ll > 0][::-1], [0], ll[ll > 0]])) if len(ll) > 2 else ll
    spread = d["t67"] - d["t33"]
    lv_sp = _levels([spread], 8)
    lv_sp = lv_sp[lv_sp >= 0] if lv_sp[0] < 0 else lv_sp
    panels = [
        (d["mean"], lv_main, CMAP[var], f"{v['label']}の気候値（平年）", f"気候値（{v['unit']}）"),
        (lo_d, lv_diff, v["cmap"], "下位1/3の境目（平年との差。これ以下は「低い」側）", f"平年との差（{v['unit']}）"),
        (hi_d, lv_diff, v["cmap"], "上位1/3の境目（平年との差。これ以上は「高い」側）", f"平年との差（{v['unit']}）"),
        (spread, lv_sp, "Purples", "境目の幅（年々のばらつきの目安）", f"{v['unit']}"),
    ]
    for rect, (f, lv, cmn, title, cl) in zip(rects, panels):
        ax = charts._ax(fig, rect, region)
        ff, ll = charts._wrap(f, lon)
        cm, nm = _cmap(cmn, lv)
        im = ax.pcolormesh(ll, lat, np.ma.masked_invalid(ff), cmap=cm, norm=nm, transform=charts.PC, shading="nearest", zorder=2)
        ax.set_title(title, fontsize=10.5)
        cb = fig.colorbar(im, ax=ax, orientation="horizontal", pad=0.04, fraction=0.045, aspect=30, extend="both")
        cb.set_label(cl, fontsize=9)
        cb.ax.tick_params(labelsize=8)
    t0 = dt.datetime.strptime(init, "%Y%m%d")
    head = f"{SERIES_LABEL[sid]} {t0:%Y年%m月%d日}" + ("基準" if sid in ("cps4", "ecmwf") else " 00Z 初期値")
    fig.suptitle(f"{head}　気候値（平年）　{label}　［{rg['label']}］", fontsize=13, y=0.97)
    foot = (f"{source_text}\n"
            f"気候値: {clim_text}。三分位は気候値の33.3/66.7%点。境目の値は「気候値＋平年との差」で、その下側が「低い」側・上側が「高い」側。境目の幅が大きい所ほど、年による振れが大きい。\n"
            "これは予報ではなく、予報を比べるための基準（平年）の図です。気象庁の公式の平年値とは別（モデル自身の過去の予報から作成）。")
    if sid == "cps4":
        foot += "\n" + cps4.COPERNICUS_NOTE.format(year=t0.year)
    if sid == "ecmwf":
        import ecmwf_seas5
        foot += "\n" + ecmwf_seas5.COPERNICUS_NOTE.format(year=t0.year)
    fig.text(0.01, 0.015, foot, fontsize=8, color="#444444", va="bottom", ha="left", linespacing=1.5)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


# ------------------------------------------------------------------ 地点の数値
def _sub(a, step):
    return a[::step, ::step]


def _list(a, nd):
    return [None if not np.isfinite(x) else round(float(x), nd) for x in a.ravel()]


def build_points(sid, init, lat, lon, labels, data):
    """東アジアの 2.5° 格子の数値（気候値・境目・今回の予報・偏差・確率）を JSON 用に作る。確率は図と同じく縮小係数を適用した値。"""
    step = 2 if len(lat) > 100 else 1                        # CPS4 は 1.25° → 2.5°・ECMWF は 1° → 2°
    la, lo = lat[::step], lon[::step]
    yi = np.where((la >= BOX[0]) & (la <= BOX[1]))[0]
    xi = np.where((lo >= BOX[2]) & (lo <= BOX[3]))[0]
    out = {"series": sid, "init": init, "lat": [float(x) for x in la[yi]], "lon": [float(x) for x in lo[xi]], "vars": {}}
    kind = sid if sid in ("cps4", "ecmwf") else "cfs"       # 校正の種類（ecmwf は開始月の校正だけ。無ければ未補正）
    for var, per in data.items():
        v = charts.VARS[var]
        nd = 3 if var == "prate" else 2
        pv = {}
        for n, d in per.items():
            alpha = (charts.load_alpha_strict if var in charts.DYN_VARS else charts.load_alpha)(n, "asia", var, init, kind)
            def g(a):
                return _sub(a, step)[np.ix_(yi, xi)]
            pu, pl = g(d["pu"]), g(d["pl"])
            if alpha is not None:
                pu, pl = charts.shrink(pu, alpha), charts.shrink(pl, alpha)
            mean = g(d["mean"])
            pv[n] = dict(label=labels[n], alpha=None if alpha is None else round(float(alpha), 2),
                         mean=_list(mean, nd), t33=_list(g(d["t33"]), nd), t67=_list(g(d["t67"]), nd),
                         fc=_list(mean + g(d["anom"]), nd), anom=_list(g(d["anom"]), nd),
                         pu=_list(np.round(pu * 100), 0), pl=_list(np.round(pl * 100), 0))
        out["vars"][var] = dict(label=v["label"], unit=v["unit"], periods=pv)
    return out


# ------------------------------------------------------------------ 実行
def run(sid, init, regions=None, make_figs=True):
    lat, lon, labels, data, clim_text, source_text = load_source(sid, init)
    regions = regions or list(charts.REGIONS)
    n = 0
    if make_figs:
        for var, per in data.items():
            for p, d in per.items():
                for rg in regions:
                    path = os.path.join(OUT, f"clim_{sid}_{init}_{var}_{p}_{rg}.png")
                    render_clim(var, rg, d, lat, lon, sid=sid, init=init, label=labels[p], clim_text=clim_text,
                                source_text=source_text, out_path=path)
                    n += 1
    pts = build_points(sid, init, lat, lon, labels, data)
    pp = os.path.join(OUT, f"pt_{sid}_{init}.json")
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(pts, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{sid} {init}: 気候値の図 {n}枚・地点の数値 {os.path.getsize(pp) / 1e3:.0f}KB", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", nargs="+", required=True, choices=["cfs_week", "cfs_month", "cps4", "ecmwf"])
    ap.add_argument("--init", required=True, help="CFS: 初期日 YYYYMMDD / CPS4: 基準日 YYYYMM01")
    ap.add_argument("--no-figs", action="store_true", help="図は作らず地点の数値だけ")
    a = ap.parse_args()
    for sid in a.series:
        run(sid, a.init, make_figs=not a.no_figs)


if __name__ == "__main__":
    main()
