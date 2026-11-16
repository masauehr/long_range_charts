"""CFSv2 の力学診断（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の月平均の偏差・確率の図を作る。

入力: data/cfs_dyn/{初期日}.npz（fetch_dyn.py）。気候値は対象と同じ月の過去の初期日（2019–2025・前後15日）から、charts.py と同じ方法で作る
  （初期日のずれの回帰補正・三分位点・メンバーの割合）。期間は charts.PERIODS（M1〜M4・Q1）。
出力: output/cfsv2_{初期日}_{変数}_{期間}_{領域}.png（変数 psi850・psi200・chi200・olr。画面の変数タブに追加される）、data/monthly_dyn_{初期日}.npz、
  output/dist_cfs_month_{初期日}.json への追記（地点の分布図）。
確率の縮小は、観測（再解析の風・補間OLR）との照合（verify_dyn.py）で求めた係数を、その変数・期間の分だけ適用する（照合が無い月・期間は**未補正**と表示）。

使い方: python dyn.py --target 20261116
"""
import argparse
import datetime as dt
import os

import numpy as np

import charts
import clim
import distview
import dyn_solver
import fetch_dyn

NOTE = {
    "psi850": "流線関数 ψ（850hPa）は風から球面のポアソン方程式を解いて算出し。北半球では ψ が正=高気圧性・負=低気圧性（南半球は逆）。",
    "psi200": "流線関数 ψ（200hPa）は風から球面のポアソン方程式を解いて算出し。北半球では ψ が正=高気圧性・負=低気圧性（南半球は逆）。ジェットの蛇行・ロスビー波列を見る。",
    "chi200": "速度ポテンシャル χ は風から算出（200hPa）。χ が負の所は上層発散（対流が活発な側）・正の所は上層収束（対流が不活発な側）。",
    "olr": "OLR は大気上端の外向き長波放射。低い所は雲頂が高い＝対流が活発、高い所は対流が不活発。",
}


def _fix_convention(arr, lat):
    """流線関数 ψ（変数0・1）・速度ポテンシャル χ（変数2）の定数項を、**全球平均0**にそろえる（気象庁の流線関数の図と同じ規約。ψ は東西平均を含む
    **全成分**）。保存済みの配列は北極0の規約だったので、ここでそろえる（何度掛けても同じ）。"""
    arr = arr.copy()
    for vi in range(3):
        arr[..., vi, :, :] = dyn_solver.remove_global_mean(arr[..., vi, :, :], lat)
    return arr


def load_samples(target, years, window, d_dir=fetch_dyn.OUT_DIR):
    """気候値用のサンプル x[サンプル, リード, 変数, 緯, 経]・初期日のずれ・年・緯度・経度（対象と同じ月の初期日だけ）。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    xs, offs, yrs = [], [], []
    lat = lon = None
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            if day.month != t.month:
                continue
            p = os.path.join(d_dir, day.strftime("%Y%m%d") + ".npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            for m in range(z["arr"].shape[0]):
                if np.isnan(z["arr"][m]).all():
                    continue
                xs.append(_fix_convention(z["arr"][m], lat))
                offs.append(d)
                yrs.append(y)
    return np.stack(xs).astype("float32"), np.array(offs, float), np.array(yrs), lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--periods", nargs="*", default=list(charts.PERIODS))
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    ap.add_argument("--vars", nargs="*", default=fetch_dyn.NAMES)
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    x, off, yr, lat, lon = load_samples(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    print(f"サンプル {len(x)}（初期日×メンバー）", flush=True)
    z = np.load(os.path.join(fetch_dyn.OUT_DIR, f"{a.target}.npz"))["arr"]
    z = z[[m for m in range(z.shape[0]) if not np.isnan(z[m]).all()]]
    z = _fix_convention(z, lat)
    names = fetch_dyn.NAMES
    dist = distview.Collector()
    summary = {}
    for p in a.periods:
        leads = charts.PERIODS[p]
        xp = x[:, leads].mean(axis=1)                      # [サンプル, 変数, 緯, 経]
        zp = z[:, leads].mean(axis=1)                      # [メンバー, 変数, 緯, 経]
        c = clim.make_clim(xp, off)
        up, lo, n = clim.tercile_prob(zp, c)
        anom = np.nanmean(zp, 0) - c["mean"]
        nm = int(np.nanmax(n))
        xa, _ = clim.adjust_offset(xp, off)
        summary[p] = dict(mean=c["mean"], t33=c["t33"], t67=c["t67"], anom=anom.astype("float32"), p_upper=up, p_lower=lo)
        for var in a.vars:
            vi = names.index(var)
            dist.add(var, p, xa[:, vi], zp[:, vi], lat, lon)
            for rg in a.regions:
                path = os.path.join(charts.OUT, f"cfsv2_{a.target}_{var}_{p}_{rg}.png")
                charts.render(var, rg, anom[vi], up[vi], lo[vi], nm, lat, lon, init=a.target,
                              label=charts.period_label(a.target, leads), out_path=path, alpha=charts.load_alpha_strict(p, rg, var, a.target),
                              calib_basis=charts.cfs_calib_texts(p, var, a.target)[0], alpha_scope="", extra_notes=NOTE[var])
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
    np.savez_compressed(os.path.join(clim.DATA, f"monthly_dyn_{a.target}.npz"), lat=lat, lon=lon, vars=names,
                        **{f"{p}_{k}": v for p, d in summary.items() for k, v in d.items()})
    print(f"保存: data/monthly_dyn_{a.target}.npz")
    dist.write("cfs_month", a.target)


if __name__ == "__main__":
    main()
