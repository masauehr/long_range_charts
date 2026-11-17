"""流線関数・速度ポテンシャル・OLR・海面水温の予報（偏差）を、気象庁の「速報」の図と同じ表示形式で描く（地域キー "jma"）。

表示形式（気象庁 https://www.data.jma.go.jp/cpd/diag/sokuho/ の月平均図に合わせる）:
  - 緯度 60°S〜60°N の横長の地図。経度は流線関数・OLR が 30°W→330°（30°W）、海面水温が 30°E→0°（太平洋中心）。灰色の太い海岸線・30度ごとの格子。
  - 陰影＝偏差（上に水平のカラーバー。青=負・赤=正）。流線関数は、予報の流線関数（全成分）の**等値線**（負は破線・正は実線・0は太線）と、**H・L**（高気圧性・低気圧性の中心）を重ねる。
    等値線の間隔: 200hPa は 10×10⁶m²/s・850hPa は 2.5×10⁶m²/s。海面水温は偏差の等値線（0.5℃ごと）。
  - 気象庁の図は実況の平年差（平年値は1991〜2020年の平均）。**この図は予報**で、偏差の基準は**モデル自身の気候値**（CFSv2: 2019–2025年の運用予報・CPS4: 1993–2020年のハインドキャスト）。
入力: data/monthly_dyn_{初期日}.npz・data/monthly_{初期日}.npz（CFS）／data/cps4_{基準日}_{変数}.npz（CPS4）。
出力: output/{cfsv2|cps4}_{初期日}_{変数}_{期間}_jma.png

使い方: python jma_style.py --series cfs_month --init 20261116
        python jma_style.py --series cps4 --init 20261101
"""
import argparse
import textwrap
import datetime as dt
import os

import numpy as np
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap
from scipy import ndimage

import charts
import clim
import cps4
import distview  # noqa: F401  （循環 import を避けるための明示。未使用）
import waf
import weekly  # noqa: F401
import matplotlib.pyplot as plt

ccrs = charts.ccrs
cfeature = charts.cfeature

SPECS = {
    "psi200": dict(name="月平均200hPa流線関数", unit="1x10⁶m²/s", lv=np.arange(-24, 25, 4), cont=10.0, lab=40.0, hl=True, wide="W"),
    "psi850": dict(name="月平均850hPa流線関数", unit="1x10⁶m²/s", lv=np.arange(-12, 13, 2), cont=2.5, lab=10.0, hl=True, wide="W"),
    "chi200": dict(name="月平均200hPa速度ポテンシャル", unit="1x10⁶m²/s", lv=np.arange(-8, 9, 2), cont=2.0, lab=None, hl=False, wide="W"),
    "olr": dict(name="月平均OLR", unit="W/m²", lv=np.arange(-60, 61, 10), cont=None, lab=None, hl=False, wide="W"),
    "sst": dict(name="月平均海面水温", unit="℃", lv=np.arange(-5.5, 5.6, 0.5), cont=0.5, lab=1.0, hl=False, wide="P", contour_anom=True),
    "pot5": dict(name="月平均海面付近(5m)の水温", unit="℃", lv=np.arange(-5.5, 5.6, 0.5), cont=0.5, lab=1.0, hl=False, wide="P", contour_anom=True),
}
CONT_NOTE = {"psi200": "等値線の間隔は10x10⁶m²/s毎（予報の流線関数）。", "psi850": "等値線の間隔は2.5x10⁶m²/s毎（予報の流線関数）。",
             "chi200": "等値線の間隔は2x10⁶m²/s毎（予報の速度ポテンシャル）。", "olr": "", "sst": "等値線は偏差の0.5℃毎。", "pot5": "等値線は偏差の0.5℃毎。"}


def cmap_bwr(n):
    """海面水温の配色（青=負・白=0付近・赤=正）。"""
    cm = LinearSegmentedColormap.from_list("sst", ["#1010ff", "#4f7cff", "#9ab6ff", "#d8e2ff", "#ffffff", "#ffd9d9", "#ff9a9a", "#ff4f4f", "#ff0000"])
    return ListedColormap([cm(x) for x in np.linspace(0, 1, n)])


def cmap_for(n):
    """JMA の速報の配色（青=負・淡い黄=0付近・橙〜赤=正）を n 階級に離散化する。"""
    cm = LinearSegmentedColormap.from_list("jma", ["#2b2bff", "#3d7bff", "#5db7ff", "#a6e2ff", "#e9f8ff", "#fffbe6", "#fff0a6", "#ffcf55", "#ff9a1c", "#ff5719", "#e00000"])
    cols = [cm(x) for x in np.linspace(0, 1, n)]
    return ListedColormap(cols)


def _shift(field, lon, start):
    """経度を start（度）から始まる 360度の並びにそろえる。戻り値: (field, lon（start 以上 start+360 未満）)。"""
    lon2 = ((lon - start) % 360) + start
    order = np.argsort(lon2)
    return field[..., order], lon2[order]


def extrema(full, lat, lon, interval):
    """流線関数の極大・極小の位置 [(lat, lon, 'H'|'L')]。北半球は極大=H・極小=L（南半球は逆）。周囲より interval 以上突出するものだけ。"""
    out = []
    size = 9 if (lon[1] - lon[0]) > 2 else 15
    mx = ndimage.maximum_filter(full, size=size, mode="wrap")
    mn = ndimage.minimum_filter(full, size=size, mode="wrap")
    mean = ndimage.uniform_filter(full, size=size * 2 + 1, mode="wrap")
    for kind, flt in (("max", mx), ("min", mn)):
        ys, xs = np.where((full == flt) & (np.abs(full - mean) > interval) & (np.abs(lat)[:, None] <= 55))
        for y, x in zip(ys, xs):
            north = lat[y] > 0
            mark = "H" if ((kind == "max") == north) else "L"
            out.append((float(lat[y]), float(lon[x]), mark))
    return out


def render(var, anom, full, lat, lon, *, title, note_lines, out_path):
    sp = SPECS[var]
    wide = sp["wide"] == "P"
    start, cl = (30.0, 195.0) if wide else (-30.0, 150.0)
    sel = (lat >= -60) & (lat <= 60)
    la = lat[sel]
    A, lo = _shift(anom[sel], lon, start)
    F, _ = _shift(full[sel], lon, start)
    A = np.concatenate([A, A[:, :1]], axis=1)
    F = np.concatenate([F, F[:, :1]], axis=1)
    lo = np.concatenate([lo, [lo[0] + 360.0]]) - cl                   # 地図座標（中心経度からの経度）で描く
    fig = plt.figure(figsize=(13.0, 6.9), dpi=100)
    ax = fig.add_axes([0.05, 0.255, 0.91, 0.62], projection=ccrs.PlateCarree(central_longitude=cl))
    half = 165 if wide else 180
    ax.set_xlim(-half, half)
    ax.set_ylim(-60, 60)
    lv = sp["lv"]
    cm = cmap_bwr(len(lv) + 1) if sp.get("contour_anom") else cmap_for(len(lv) + 1)
    norm = BoundaryNorm(lv, len(lv) + 1)
    cs = ax.contourf(lo, la, np.ma.masked_invalid(A), levels=np.concatenate([[min(-1e3, float(np.nanmin(A)) - 1)], lv, [max(1e3, float(np.nanmax(A)) + 1)]]), colors=[cm(i) for i in range(len(lv) + 1)], zorder=1)
    ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="none", zorder=2)
    ax.coastlines(resolution="110m", linewidth=2.0, color="#666666", zorder=6)
    gl = ax.gridlines(draw_labels=False, linewidth=0.5, color="#888888", alpha=0.6, linestyle=":",
                      xlocs=np.arange(-180, 361, 30), ylocs=np.arange(-60, 61, 30), zorder=3)
    # 等値線
    if sp.get("cont"):
        src = ndimage.gaussian_filter(np.nan_to_num(A), 1.0) if sp.get("contour_anom") else F      # 海面水温の等値線は、海岸付近の細かい乱れを抑えるため軽く平滑化
        if sp.get("contour_anom"):
            src = np.where(np.isfinite(A), src, np.nan)
        step = sp["cont"]
        levels = np.arange(np.floor(np.nanmin(src) / step) * step, np.nanmax(src) + step, step)
        levels = levels[np.abs(levels) < 1e6]
        neg = [l for l in levels if l < 0]
        pos = [l for l in levels if l > 0]
        kw = dict(colors="k", zorder=4)
        if neg:
            ax.contour(lo, la, np.ma.masked_invalid(src), levels=neg, linestyles="dashed", linewidths=0.8, **kw)
        if pos:
            ax.contour(lo, la, np.ma.masked_invalid(src), levels=pos, linestyles="solid", linewidths=0.9, **kw)
        z = ax.contour(lo, la, np.ma.masked_invalid(src), levels=[0.0], linestyles="solid", linewidths=(1.2 if sp.get("contour_anom") else 2.0), **kw)
        if sp.get("lab"):
            labl = [l for l in levels if abs(l / sp["lab"] - round(l / sp["lab"])) < 1e-6]
            c2 = ax.contour(lo, la, np.ma.masked_invalid(src), levels=labl, linewidths=0, colors="k", zorder=4)
            ax.clabel(c2, labl, inline=True, fontsize=8, fmt="%g")
    # H・L
    if sp.get("hl"):
        for (y, x, m) in extrema(F[:, :-1], la, lo[:-1], sp["cont"] * 2.0):
            ax.text(((x - start) % 360) + start - cl, y, m, fontsize=13, family="serif", ha="center", va="center", zorder=7,
                    bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.0))
    # 軸の目盛り
    xs = np.arange(-half, half + 1, 30)
    ax.set_xticks(xs)
    ax.set_xticklabels([_lon_label(x + cl) for x in xs], fontsize=10)
    ax.set_yticks([-60, -30, 0, 30, 60])
    ax.set_yticklabels(["60°S", "30°S", "0°" if not wide else "EQ", "30°N", "60°N"], fontsize=10)
    ax.xaxis.set_ticks_position("both")
    ax.yaxis.set_ticks_position("both")
    # カラーバー（上）
    cax = fig.add_axes([0.05, 0.915, 0.56, 0.027])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cm), cax=cax, orientation="horizontal", extend="both", ticks=lv[::2] if len(lv) > 13 else lv)
    cb.ax.tick_params(labelsize=9)
    fig.text(0.63, 0.9285, f"anomalies({sp['unit']})", fontsize=10, va="center")
    fig.text(0.05, 0.205, title, fontsize=13, fontweight="bold", va="top")
    note_lines = [seg for line in note_lines for seg in textwrap.wrap(line, 150)]
    fig.text(0.05, 0.168, "\n".join(note_lines), fontsize=8.2, color="#444444", va="top", linespacing=1.45)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


# ------------------------------------------------------------------ 速度ポテンシャルの複合図（気象庁の「異常気象分析検討会」の図の形式）
A_EARTH = 6.371e6
OLR_LV = np.array([-40, -32, -24, -16, -8, 8, 16, 24, 32, 40])


def divergent_wind(chi_anom, lat, lon):
    """速度ポテンシャルの偏差（10⁶ m²/s）から発散風の偏差（m/s）(u, v)。u=(1/(a cosφ))∂χ/∂λ・v=(1/a)∂χ/∂φ。"""
    chi = np.asarray(chi_anom, "float64") * 1e6
    phi = np.deg2rad(lat)
    dl = np.deg2rad(lon[1] - lon[0])
    dchi_dl = (np.roll(chi, -1, axis=1) - np.roll(chi, 1, axis=1)) / (2 * dl)
    with np.errstate(divide="ignore", invalid="ignore"):
        u = dchi_dl / (A_EARTH * np.cos(phi)[:, None])
    v = np.gradient(chi, phi, axis=0) / A_EARTH
    u[np.abs(lat) > 80] = np.nan
    return u, v


def render_chi_composite(chi, psi, olr, lat, lon, *, title, note_lines, out_path, psi_mean=None, chi_mean=None):
    """上段(a) 速度ポテンシャル偏差の等値線（0.5×10⁶m²/s毎・緑=負/茶=正）と発散風の偏差（矢印）・下段(b) 200hPa流線関数偏差の等値線（3×10⁶m²/s毎）・
    陰影は両方ともOLR偏差（W/m²）。アジア〜太平洋域。気象庁の図（第3.2-5図の形式）に合わせた。"""
    start, cl = 20.0, 135.0
    x0, x1, y0, y1 = 30.0, 250.0, -30.0, 60.0
    sel = (lat >= -35) & (lat <= 65)
    la = lat[sel]

    def prep(f):
        g, lo = _shift(f[sel], lon, start)
        return np.concatenate([g, g[:, :1]], axis=1), np.concatenate([lo, [lo[0] + 360.0]]) - cl
    C, X = prep(chi)
    P, _ = prep(psi)
    O, _ = prep(olr)
    u, v = divergent_wind(chi, lat, lon)
    U, _ = prep(u)
    V, _ = prep(v)
    wafx = wafy = None
    if psi_mean is not None and chi_mean is not None:                    # 波の活動度フラックス（下段(b)の矢印）
        uc, vc = waf.wind_from_psi_chi(psi_mean, chi_mean, lat, lon)
        wx, wy = waf.wave_activity_flux(psi, uc, vc, lat, lon, p_hpa=200.0)
        wx[np.abs(lat) < 10], wy[np.abs(lat) < 10] = np.nan, np.nan       # 赤道付近は理論が成り立たない
        wafx, _ = prep(wx)
        wafy, _ = prep(wy)
    cm = cmap_for(len(OLR_LV) + 1)
    norm = BoundaryNorm(OLR_LV, len(OLR_LV) + 1)
    fig = plt.figure(figsize=(9.6, 11.4), dpi=100)
    axes = [fig.add_axes([0.07, 0.505, 0.9, 0.395], projection=ccrs.PlateCarree(central_longitude=cl)),
            fig.add_axes([0.07, 0.115, 0.9, 0.38], projection=ccrs.PlateCarree(central_longitude=cl))]
    lvl = np.concatenate([[min(-1e3, float(np.nanmin(O)) - 1)], OLR_LV, [max(1e3, float(np.nanmax(O)) + 1)]])
    for k, ax in enumerate(axes):
        ax.set_xlim(x0 - cl, x1 - cl)
        ax.set_ylim(y0, y1)
        ax.contourf(X, la, np.ma.masked_invalid(O), levels=lvl, colors=[cm(i) for i in range(len(OLR_LV) + 1)], zorder=1)
        ax.coastlines(resolution="110m", linewidth=2.0, color="#777777", zorder=6)
        ax.axhline(0, color="#d02020", lw=0.9, zorder=5)
        ax.gridlines(draw_labels=False, linewidth=0.4, color="#888888", alpha=0.5, linestyle=":", xlocs=np.arange(-180, 361, 30), ylocs=np.arange(-30, 61, 30), zorder=3)
        xs = np.arange(60, 241, 30)
        ax.set_xticks(xs - cl)
        ax.set_xticklabels([_lon_label(x) for x in xs], fontsize=10)
        ax.set_yticks([-30, 0, 30, 60])
        ax.set_yticklabels(["30°S", "0°", "30°N", "60°N"], fontsize=10)
        ax.text(0.015, 0.95, "(a) CHI200" if k == 0 else "(b) PSI200", transform=ax.transAxes, fontsize=14, va="top", zorder=9,
                bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="black", lw=1.0))
    ax = axes[0]
    step = 0.5
    lv = np.arange(np.floor(np.nanmin(C) / step) * step, np.nanmax(C) + step, step)
    neg, pos = [x for x in lv if x < -1e-9], [x for x in lv if x > 1e-9]
    if neg:
        ax.contour(X, la, np.ma.masked_invalid(C), levels=neg, colors="#2e9b3a", linewidths=0.9, zorder=4)
    if pos:
        ax.contour(X, la, np.ma.masked_invalid(C), levels=pos, colors="#7a1f1f", linewidths=0.9, zorder=4)
    ax.contour(X, la, np.ma.masked_invalid(C), levels=[0.0], colors="#7a1f1f", linewidths=2.0, zorder=4)
    ss = max(int(round(10.0 / abs(lon[1] - lon[0]))), 1)            # 矢印は10°おき
    Us, Vs = U[::ss, ::ss].copy(), V[::ss, ::ss].copy()
    weak = np.hypot(Us, Vs) < 0.3                                      # 弱い矢印は描かない
    Us[weak], Vs[weak] = np.nan, np.nan
    q = ax.quiver(X[::ss], la[::ss], np.ma.masked_invalid(Us), np.ma.masked_invalid(Vs), color="#8a2be2", width=0.0025, scale=45, zorder=7)
    ax.quiverkey(q, 0.9, 1.03, 2.0, "2 m/s", labelpos="E", fontproperties=dict(size=9))
    bx = axes[1]
    step = 3.0
    lv = np.arange(np.floor(np.nanmin(P) / step) * step, np.nanmax(P) + step, step)
    neg, pos = [x for x in lv if x < -1e-9], [x for x in lv if x > 1e-9]
    if neg:
        bx.contour(X, la, np.ma.masked_invalid(P), levels=neg, colors="k", linestyles="dashed", linewidths=0.8, zorder=4)
    if pos:
        bx.contour(X, la, np.ma.masked_invalid(P), levels=pos, colors="k", linestyles="solid", linewidths=0.9, zorder=4)
    bx.contour(X, la, np.ma.masked_invalid(P), levels=[0.0], colors="k", linewidths=2.2, zorder=4)
    if wafx is not None:
        Wx, Wy = wafx[::ss, ::ss], wafy[::ss, ::ss]
        mag = np.hypot(Wx, Wy)
        ok = mag[np.isfinite(mag)]
        if ok.size:
            q90 = float(np.percentile(ok, 90))
            key = min([k for k in (2, 5, 10, 20, 40, 80, 160) if k >= q90] or [160])
            qb = bx.quiver(X[::ss], la[::ss], np.ma.masked_invalid(Wx), np.ma.masked_invalid(Wy), color="#6a1b9a", width=0.0025,
                           scale_units="width", scale=key / 0.09, zorder=7)
            bx.quiverkey(qb, 0.62, 1.035, key, f"{key} m²/s²（波の活動度フラックス）", labelpos="E", fontproperties=dict(size=9))
    cax = fig.add_axes([0.07, 0.945, 0.6, 0.016])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cm), cax=cax, orientation="horizontal", extend="both", ticks=OLR_LV)
    cb.ax.tick_params(labelsize=9)
    fig.text(0.69, 0.953, "(W/m²)  陰影: OLR偏差", fontsize=10, va="center")
    fig.text(0.07, 0.092, title, fontsize=11, fontweight="bold", va="top", linespacing=1.4)
    note_lines = [seg for line in note_lines for seg in textwrap.wrap(line, 100)]
    fig.text(0.07, 0.05, "\n".join(note_lines), fontsize=8.0, color="#444444", va="top", linespacing=1.45)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _lon_label(lon):
    x = ((lon + 180) % 360) - 180
    if abs(x) < 1e-9:
        return "0°"
    if abs(abs(x) - 180) < 1e-9:
        return "180°"
    return f"{abs(int(round(x)))}°{'E' if x > 0 else 'W'}"


# ------------------------------------------------------------------ 入力
def load(series, init):
    """戻り値: ({変数: {期間: dict(mean, anom)}}, lat, lon, {期間: ラベル}, 出典の文, 気候値の説明, 初期の文)。"""
    if series == "cfs_month":
        data, lat, lon = {}, None, None
        for fname in (f"monthly_{init}.npz", f"monthly_dyn_{init}.npz"):
            p = os.path.join(clim.DATA, fname)
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            for vi, v in enumerate(str(x) for x in z["vars"]):
                if v in SPECS:
                    data[v] = {n: dict(mean=z[f"{n}_mean"][vi], anom=z[f"{n}_anom"][vi]) for n in charts.PERIODS}
        labels = {n: charts.period_label(init, charts.PERIODS[n]) for n in charts.PERIODS}
        d = dt.datetime.strptime(init, "%Y%m%d")
        return data, lat, lon, labels, "NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。", \
            f"偏差の基準はモデルの気候値（CFSv2の運用予報 2019–2025年の同月の初期日・約7年）。", f"CFSv2 {d:%Y年%m月%d日} 00Z 初期値（4メンバー）"
    if series == "cfs_week":
        data, lat, lon = {}, None, None
        for fname in (f"weekly_{init}.npz", f"weekly_dyn_{init}.npz"):
            p = os.path.join(clim.DATA, fname)
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            for vi, v in enumerate(str(x) for x in z["vars"]):
                if v in SPECS:
                    data[v] = {n: dict(mean=z[f"{n}_mean"][vi], anom=z[f"{n}_anom"][vi]) for n in weekly.WEEKS}
        labels = {n: weekly.span_label(init, weekly.WEEKS[n]) for n in weekly.WEEKS}
        d = dt.datetime.strptime(init, "%Y%m%d")
        return data, lat, lon, labels, "NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。", \
            "偏差の基準はモデルの気候値（CFSv2の運用予報 2019–2025年の前後7日の初期日・約7年）。", f"CFSv2 {d:%Y年%m月%d日} 00Z 初期値（4メンバー）"
    periods = cps4.make_periods(int(init[4:6]))
    data, lat, lon = {}, None, None
    for v in SPECS:
        p = os.path.join(clim.DATA, f"cps4_{init}_{v}.npz")
        if not os.path.exists(p):
            continue
        z = np.load(p)
        lat, lon = z["lat"], z["lon"]
        data[v] = {n: dict(mean=z[f"{n}_mean"], anom=z[f"{n}_anom"]) for n in ("L1", "L2", "L3", "L4", "L2-4")}
    labels = {n: periods[n][1] for n in ("L1", "L2", "L3", "L4", "L2-4")}
    d = dt.datetime.strptime(init, "%Y%m%d")
    return data, lat, lon, labels, "JMA/MRI-CPS4（Copernicus C3S 経由）を加工して作成。気象庁・C3Sの推奨を示すものではない。", \
        "偏差の基準はモデルの気候値（CPS4 のハインドキャスト 1993–2020年・28年×10メンバー）。", f"JMA CPS4 {d:%Y年%m月%d日}基準（155メンバー）"


def run(series, init, only=None):
    data, lat, lon, labels, source, basis, head = load(series, init)
    prefix = "cps4" if series == "cps4" else "cfsv2"
    n = 0
    for var, per in data.items():
        if only and var not in only:
            continue
        sp = SPECS[var]
        for p, d in per.items():
            anom = d["anom"]
            full = d["mean"] + anom
            note = [f"{sp['name']}・平年差の予報（{labels[p]}）。陰影は偏差（モデルの気候値との差）。" + CONT_NOTE[var],
                    f"{source}{basis}",
                    "気象庁の速報（実況の解析）と同じ表示形式で描いた予報です。気象庁の公式予報ではなく、個々の日の天気は予測できません。確率の図は「予報（偏差・確率）」を見てください。"]
            if series == "cps4":
                note += ["Contains modified Copernicus Climate Change Service information %d." % int(init[:4]),
                         "Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains."]
            path = os.path.join(charts.OUT, f"{prefix}_{init}_{var}_{p}_jma.png")
            if var == "chi200":                                  # 速度ポテンシャルは、気象庁の複合図（発散風・OLR・流線関数）の形式
                if "psi200" not in data or "olr" not in data:
                    continue
                note = ["(a) 200hPa速度ポテンシャルの予報の偏差（等値線: 0.5x10⁶m²/s毎・緑=負[発散]・茶=正[収束]）と発散風の偏差（矢印）、(b) 200hPa流線関数の偏差（等値線: 3x10⁶m²/s毎）と波の活動度フラックス（矢印）。",
                        f"陰影は(a)(b)とも OLR の偏差（{labels[p]}）。(b) の矢印は波の活動度フラックス（Takaya-Nakamura・200hPa・基本場の風が3m/s未満の所と赤道付近は描かない）。気象庁の図（異常気象分析検討会の形式）に合わせた予報。",
                        f"{source}{basis}", "気象庁の公式予報ではなく、個々の日の天気は予測できません。"]
                if series == "cps4":
                    note += ["Contains modified Copernicus Climate Change Service information %d. Neither the European Commission nor ECMWF is responsible" % int(init[:4]),
                             "for any use that may be made of the Copernicus information or data it contains."]
                render_chi_composite(anom, data["psi200"][p]["anom"], data["olr"][p]["anom"], lat, lon,
                                     psi_mean=data["psi200"][p]["mean"], chi_mean=full - anom,
                                     title=f"200hPa速度ポテンシャル・流線関数の平年差（予報: {labels[p]}）\n{head}", note_lines=note, out_path=path)
                n += 1
                continue
            render(var, anom, full, lat, lon, title=f"{sp['name']}・平年差（予報: {labels[p]}）　{head}", note_lines=note, out_path=path)
            n += 1
    print(f"{series} {init}: 気象庁形式の図 {n}枚", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True, choices=["cfs_week", "cfs_month", "cps4"])
    ap.add_argument("--init", required=True)
    ap.add_argument("--vars", nargs="*")
    a = ap.parse_args()
    run(a.series, a.init, a.vars)


if __name__ == "__main__":
    main()
