"""L2 図（期間平均の偏差と三分位確率）の作図。

期間は CFSv2 月平均ファイルの暦月（初月は初期日以降の部分月。stepRange の表記と中身は一致しない: 日別データで検証済み）。
  M1=初期月の残り（初期日〜月末）, M2=翌月, M3=翌々月, M4=3か月後の月, Q1=M2〜M4の3か月平均
1枚に 偏差 / 上位三分位の確率 / 下位三分位の確率 の3面を並べる。
00Z の4メンバーだけが4か月先（M4）まであるため、期間は M4 までに限る。

使い方:
    python charts.py --target 20261112
    python charts.py --target 20261112 --periods M1 Q1 --regions asia --vars t2m
"""
import argparse
import datetime as dt
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.colors import BoundaryNorm, ListedColormap

import calib
import clim
import distview

plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

PC = ccrs.PlateCarree()
OUT = os.path.join(clim.ROOT, "output")

# 期間: 名前 -> 使う月平均ファイルのリード（暦月。リード0は初期日以降の部分月）
PERIODS = {"M1": [0], "M2": [1], "M3": [2], "M4": [3], "Q1": [1, 2, 3]}
REGIONS = {
    "asia": dict(label="東アジア", extent=(95, 175, 8, 62), fig=(15, 6.0), rect_y=(0.27, 0.63),
                 proj=lambda: ccrs.LambertConformal(central_longitude=125, central_latitude=40,
                                                    standard_parallels=(25, 55))),
    "global": dict(label="全球", extent=None, fig=(15, 5.0), rect_y=(0.31, 0.58), proj=lambda: ccrs.Robinson(central_longitude=180)),
}
# 変数: 名前 -> 表示名, 単位, 偏差の刻み, 上位/下位の色（上位=多い/高い側）
VARS = {
    "t2m": dict(label="2m気温", unit="℃", lv=[-4, -3, -2, -1, -0.5, 0.5, 1, 2, 3, 4], cmap="RdBu_r",
                up=("Reds", "高い"), lo=("Blues", "低い")),
    "prate": dict(label="降水量", unit="mm/日", lv=[-3, -2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2, 3], cmap="BrBG",
                  up=("Greens", "多い"), lo=("YlOrBr", "少ない")),
    "z500": dict(label="500hPa高度", unit="gpm", lv=[-90, -60, -30, -15, -7.5, 7.5, 15, 30, 60, 90], cmap="RdBu_r",
                 up=("Reds", "高い"), lo=("Blues", "低い")),
    "sst": dict(label="海面水温", unit="℃", lv=[-3, -2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2, 3],
                cmap="RdBu_r", up=("Reds", "高い"), lo=("Blues", "低い")),
    # 力学診断（流線関数・速度ポテンシャル・OLR。dyn.py / cps4_dyn.py）。北半球では ψ が正=高気圧性・負=低気圧性（南半球は逆）。
    "psi850": dict(label="流線関数（850hPa）", unit="10⁶ m²/s", lv=[-8, -4, -2, -1, -0.5, 0.5, 1, 2, 4, 8], cmap="RdBu_r",
                   up=("Reds", "正（高気圧性）"), lo=("Blues", "負（低気圧性）")),
    "psi200": dict(label="流線関数（200hPa）", unit="10⁶ m²/s", lv=[-20, -10, -5, -2, -1, 1, 2, 5, 10, 20], cmap="RdBu_r",
                   up=("Reds", "正（高気圧性）"), lo=("Blues", "負（低気圧性）")),
    "chi200": dict(label="速度ポテンシャル（200hPa）", unit="10⁶ m²/s", lv=[-6, -4, -2, -1, -0.5, 0.5, 1, 2, 4, 6], cmap="PuOr_r",
                   up=("Oranges", "正（収束）"), lo=("Purples", "負（発散）")),
    "olr": dict(label="OLR（外向き長波放射）", unit="W/m²", lv=[-30, -20, -10, -5, -2.5, 2.5, 5, 10, 20, 30], cmap="BrBG_r",
                up=("YlOrBr", "高い（不活発）"), lo=("GnBu", "低い（活発）")),
    "pot5": dict(label="海面付近の水温(5m)", unit="℃", lv=[-3, -2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2, 3],
                 cmap="RdBu_r", up=("Reds", "高い"), lo=("Blues", "低い")),
}
PROB_LV = [0, 33.4, 40, 50, 60, 70, 80, 90, 100.1]


def period_label(init, leads):
    """リード（暦月）を「11月（11/12〜11/30）の平均」「12〜2月の3か月平均」のような表記にする。"""
    d0 = dt.datetime.strptime(init, "%Y%m%d").date()

    def month(k):
        return (d0.month - 1 + k) % 12 + 1

    if len(leads) == 1:
        k = leads[0]
        if k == 0:
            last = (dt.date(d0.year + d0.month // 12, d0.month % 12 + 1, 1) - dt.timedelta(days=1)).day
            return f"{month(0)}月（{d0.month}/{d0.day}〜{d0.month}/{last}）の平均"
        return f"{month(k)}月の月平均"
    return f"{month(leads[0])}〜{month(leads[-1])}月の{len(leads)}か月平均"


def _anom_cmap(lv, name):
    cm = plt.get_cmap(name)
    n = len(lv) + 1
    cols = [cm(x) for x in np.linspace(0.02, 0.98, n)]
    cols[n // 2] = (1, 1, 1, 1)               # 0付近は白
    return ListedColormap(cols), BoundaryNorm(lv, n)


def _prob_cmap(name):
    cm = plt.get_cmap(name)
    cols = [(0.95, 0.95, 0.95, 1)] + [cm(x) for x in np.linspace(0.25, 0.95, len(PROB_LV) - 2)]
    return ListedColormap(cols), BoundaryNorm(PROB_LV, len(cols))


def _ax(fig, rect, region):
    r = REGIONS[region]
    ax = fig.add_axes(rect, projection=r["proj"]())
    ax.set_extent(r["extent"], crs=PC) if r["extent"] else ax.set_global()
    ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#f4f1e8", zorder=0)
    ax.coastlines(resolution="110m", linewidth=0.5, color="#555555", zorder=6)
    ax.gridlines(draw_labels=False, linewidth=0.3, color="#999999", alpha=0.6,
                 xlocs=range(-180, 181, 30), ylocs=range(-80, 81, 10))
    return ax


def _wrap(field, lon):
    """経度360度側へ1列足して日付変更線のすき間を防ぐ。"""
    return np.concatenate([field, field[:, :1]], axis=1), np.concatenate([lon, [360.0]])


CAL_PATH = calib.PATH
CAL_DAYS = calib.DAYS     # CFS: 校正した初期日からこの日数以内の初期日にだけ縮小係数を適用する


def _slot(target, kind):
    """対象に合う校正（calibration.json の中身の一部）。無ければ None。

    cfs: 対象の初期日に月日で最も近い校正（前後 CAL_DAYS 日以内）。cps4・ecmwf: 対象の開始月と同じ月の校正。
    target を渡さなければ（None）最初の校正（従来の動作・テスト用）。
    """
    cal = calib.load(CAL_PATH)
    if kind == "cps4":
        return calib.cps4_slot(cal, None if target is None else int(target[4:6]))[1]
    if kind == "ecmwf":                                   # ECMWF SEAS5: 校正した開始月の係数だけ（無ければ None＝未補正。CFS の校正は当てない）
        return calib.ecmwf_slot(cal, None if target is None else int(target[4:6]))[1]
    return calib.cfs_slot(cal, target, CAL_DAYS)[1]


def calib_valid(target=None, kind="cfs"):
    """縮小係数を適用してよい初期日か（季節に合う校正があるか）。"""
    return _slot(target, kind) is not None


def load_alpha(name, region, var=None, target=None, kind="cfs"):
    """観測照合で求めた確率の縮小係数 α。無ければ None（未補正）。

    var を渡すと、その変数自身の照合による係数（alpha_var）を優先し、無ければ2m気温の係数（alpha）を使う。
    """
    slot = _slot(target, kind)
    if slot is None:
        return None
    key = "asia" if region == "asia" else "global"
    try:
        av = slot.get("alpha_var", {}).get(var or "", {})
        if var and name in av:
            return av[name][key]
        return slot["alpha"][name][key]
    except KeyError:
        return None


def has_var_alpha(name, var, target=None, kind="cfs"):
    """その変数自身の照合による係数があるか（CFS の2m気温は alpha が照合済みの係数）。校正が無ければ False。"""
    slot = _slot(target, kind)
    if slot is None:
        return False
    if var == "t2m" and kind == "cfs":
        return name in slot.get("alpha", {})
    return name in slot.get("alpha_var", {}).get(var, {})


DYN_VARS = {"psi850", "psi200", "chi200", "olr"}      # 力学診断（dyn.py / cps4_dyn.py）


def load_alpha_strict(name, region, var, target=None, kind="cfs"):
    """その変数自身の照合による縮小係数だけを返す（無ければ None＝未補正。2m気温の係数への代用はしない）。力学診断で使う。"""
    if not has_var_alpha(name, var, target, kind):
        return None
    return load_alpha(name, region, var, target, kind)


CFS_OBS = {   # CFS の窓種別（週=W/J・月=M/Q）と変数 -> 照合に使った観測
    ("week", "t2m"): "再解析の2m気温", ("week", "prate"): "再解析の降水（精度は低め）", ("week", "z500"): "再解析のZ500",
    ("month", "t2m"): "再解析の2m気温", ("month", "prate"): "GPCPの降水", ("month", "z500"): "再解析のZ500",
    ("month", "pot5"): "ERSSTv5の海面水温",
    ("month", "psi850"): "再解析の風から算出した流線関数", ("month", "psi200"): "再解析の風から算出した流線関数",
    ("month", "chi200"): "再解析の風から算出した速度ポテンシャル", ("month", "olr"): "NOAA補間OLR",
}


def cfs_calib_texts(name, var, target=None):
    """CFS の図の下端に出す、縮小係数の根拠の文言と適用範囲の補足。戻り値: (calib_basis, alpha_scope)"""
    if has_var_alpha(name, var, target):
        kind = "week" if name[0] in "WJ" else "month"
        return f"過去7年の観測（{CFS_OBS.get((kind, var), '観測')}）との照合", ""
    return "過去7年の観測（再解析の2m気温）との照合", "。2m気温の係数を仮に適用"


def shrink(p, alpha):
    """確率を気候値(1/3)へ縮める: p' = 1/3 + α(p - 1/3)。"""
    return 1 / 3 + alpha * (p - 1 / 3)


CLIM_TEXT_MONTHLY = "CFSv2の運用予報 2019–2025年の同月の初期日（初期日のずれを補正）・約7年"


def render(var, region, anom, pu, pl, n_members, lat, lon, *, init, label, out_path, clim_text=CLIM_TEXT_MONTHLY,
           member_text=None, alpha=None, title_text=None, source_text=None, extra_notes=None,
           calib_basis="過去7年の観測（再解析の2m気温）との照合", alpha_scope="。他の変数にも仮に適用"):
    v = VARS[var]
    if alpha is not None:
        pu, pl = shrink(pu, alpha), shrink(pl, alpha)
    rg = REGIONS[region]
    fig = plt.figure(figsize=rg["fig"], dpi=100)
    y, h = rg["rect_y"]
    rects = [[0.01, y, 0.31, h], [0.345, y, 0.31, h], [0.68, y, 0.31, h]]
    cm_a, nm_a = _anom_cmap(v["lv"], v["cmap"])
    cm_u, nm_u = _prob_cmap(v["up"][0])
    cm_l, nm_l = _prob_cmap(v["lo"][0])
    panels = [
        (anom, cm_a, nm_a, f"偏差（{v['unit']}）", "max", f"{v['label']}の偏差（気候値との差）"),
        (pu * 100, cm_u, nm_u, "確率（%）", "neither", f"{v['label']}が「{v['up'][1]}」側（上位1/3）の確率"),
        (pl * 100, cm_l, nm_l, "確率（%）", "neither", f"{v['label']}が「{v['lo'][1]}」側（下位1/3）の確率"),
    ]
    for rect, (f, cm, nm, cl, ext, title) in zip(rects, panels):
        ax = _ax(fig, rect, region)
        ff, ll = _wrap(f, lon)
        im = ax.pcolormesh(ll, lat, np.ma.masked_invalid(ff), cmap=cm, norm=nm, transform=PC,
                           shading="nearest", zorder=2)
        ax.set_title(title, fontsize=11)
        cb = fig.colorbar(im, ax=ax, orientation="horizontal", pad=0.04, fraction=0.045, aspect=30)
        cb.set_label(cl, fontsize=9)
        if "確率" in cl:
            cb.set_ticks([0, 33.4, 40, 50, 60, 70, 80, 90, 100])
            cb.set_ticklabels(["0", "33", "40", "50", "60", "70", "80", "90", "100"])
        cb.ax.tick_params(labelsize=8)
    t0 = dt.datetime.strptime(init, "%Y%m%d")
    title_text = title_text or f"CFSv2 {t0:%Y年%m月%d日} 00Z 初期値"
    fig.suptitle(f"{title_text}  {label}  ［{REGIONS[region]['label']}］",
                 fontsize=13, y=0.97)
    member_text = member_text or f"メンバー{n_members}（00Z）のため確率は25%刻み。"
    source_text = source_text or "NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。"
    foot = (f"{source_text}{member_text}\n"
            f"気候値: {clim_text}。三分位は気候値の33.3/66.7%点。"
            f"気象庁の公式予報（高い/平年並/低い）ではない。期間平均の傾向であり、個々の日の天気は予測できない。\n"
            + (f"確率は、{calib_basis}で自信過剰と分かったため、気候値(1/3)へ縮小済み（係数{alpha:.2f}{alpha_scope}）。"
               if alpha is not None else "確率は未補正（観測との照合が無い窓）。")
            + (("\n" + extra_notes) if extra_notes else ""))
    fig.text(0.01, 0.015, foot, fontsize=8, color="#444444", va="bottom", ha="left", linespacing=1.5)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--periods", nargs="*", default=list(PERIODS))
    ap.add_argument("--regions", nargs="*", default=list(REGIONS))
    ap.add_argument("--vars", nargs="*", default=list(clim.VARS), help="CFS月平均の変数（t2m・prate・z500・pot5）")
    ap.add_argument("--detrend", action="store_true", help="全球平均の経年トレンドを補正（既定はオフ。検算で改善なし）")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    x, off, yr, lat, lon = clim.load_samples(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    if a.detrend:
        x, _ = clim.trend_adjust(x, yr, int(a.target[:4]), lat)
    z = np.load(os.path.join(clim.CF_DIR, f"{a.target}.npz"))["arr"]
    names = list(clim.VARS)
    dist = distview.Collector()                 # 地点の分布図のデータ
    summary = {}                                # 期間 -> 統計（気候値の閲覧用に保存する。climview.py が読む）
    for p in a.periods:
        leads = PERIODS[p]
        xp = x[:, leads].mean(axis=1)               # [サンプル, 変数, 緯, 経]（NaNを含むサンプルはNaN）
        zp = z[:, leads].mean(axis=1)               # [メンバー, 変数, 緯, 経]
        c = clim.make_clim(xp, off)
        up, lo, n = clim.tercile_prob(zp, c)
        anom = np.nanmean(zp, 0) - c["mean"]
        nm = int(np.nanmax(n))
        xa, _ = clim.adjust_offset(xp, off)
        for var in a.vars:
            dist.add(var, p, xa[:, names.index(var)], zp[:, names.index(var)], lat, lon)
        summary[p] = dict(mean=c["mean"], t33=c["t33"], t67=c["t67"], anom=anom.astype("float32"), p_upper=up, p_lower=lo)
        for var in a.vars:
            vi = names.index(var)
            for rg in a.regions:
                path = os.path.join(OUT, f"cfsv2_{a.target}_{var}_{p}_{rg}.png")
                render(var, rg, anom[vi], up[vi], lo[vi], nm, lat, lon, init=a.target,
                       label=period_label(a.target, leads), out_path=path, alpha=load_alpha(p, rg, var, a.target),
                       calib_basis=cfs_calib_texts(p, var, a.target)[0], alpha_scope=cfs_calib_texts(p, var, a.target)[1])
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
    np.savez_compressed(os.path.join(clim.DATA, f"monthly_{a.target}.npz"), lat=lat, lon=lon, vars=names,
                        **{f"{p}_{k}": v for p, d in summary.items() for k, v in d.items()})
    print(f"保存: data/monthly_{a.target}.npz")
    dist.write("cfs_month", a.target)


if __name__ == "__main__":
    main()
