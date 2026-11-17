"""CFSv2 の力学診断（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の週平均（W1〜W4）の偏差・確率の図を作る。

入力: data/cfs_dyn_daily/{初期日}.npz（fetch_dyn_daily.py。NOAA が計算した ψ・χ・OLR の日平均）。気候値は weekly.py と同じ方法
  （前後7日の初期日×過去7年×メンバー・初期日のずれの回帰補正・三分位・メンバーの割合）。
出力: output/cfsv2_{初期日}_{変数}_{W1〜W4}_{asia|global}.png・data/weekly_dyn_{初期日}.npz・output/dist_cfs_week_{初期日}.json への追記。
確率の縮小は、観測照合（日別の観測との照合）がまだ無いので**未補正**（図に「未補正」と出る）。

使い方: python weekly_dyn.py --target 20261116
"""
import argparse
import datetime as dt
import os

import numpy as np

import charts
import clim
import distview
import dyn
import fetch_dyn_daily
import weekly

DIR = fetch_dyn_daily.OUT_DIR
NAMES = fetch_dyn_daily.NAMES


def load_daily(target, years, window):
    """x[サンプル, 日, 変数, 緯, 経]・初期日のずれ・年・緯度・経度（メンバー展開済み）。weekly.load_daily と同じ順序。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    xs, offs, yrs = [], [], []
    lat = lon = None
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            p = os.path.join(DIR, day.strftime("%Y%m%d") + ".npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            lat, lon = z["lat"], z["lon"]
            for m in range(z["arr"].shape[0]):
                if np.isnan(z["arr"][m]).all():
                    continue
                xs.append(z["arr"][m])
                offs.append(d)
                yrs.append(y)
    return np.stack(xs), np.array(offs, float), np.array(yrs), lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    ap.add_argument("--weeks", nargs="*", default=list(weekly.WEEKS))
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    x, off, yr, lat, lon = load_daily(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    print(f"サンプル {len(x)}（初期日×メンバー）", flush=True)
    z = np.load(os.path.join(DIR, f"{a.target}.npz"))["arr"]
    z = z[[m for m in range(z.shape[0]) if not np.isnan(z[m]).all()]]
    nm = int(z.shape[0])
    dist = distview.Collector()
    summary = {}
    for name in a.weeks:
        span = weekly.WEEKS[name]
        c, anom, up, lo, zp = weekly.window_stats(x, off, z, span)
        summary[name] = dict(mean=c["mean"], t33=c["t33"], t67=c["t67"], anom=anom.astype("float32"), p_upper=up, p_lower=lo)
        xa, _ = clim.adjust_offset(x[:, span[0] - 1:span[1]].mean(axis=1), off)
        for vi, var in enumerate(NAMES):
            dist.add(var, name, xa[:, vi], zp[:, vi], lat, lon)
            for rg in a.regions:
                path = os.path.join(charts.OUT, f"cfsv2_{a.target}_{var}_{name}_{rg}.png")
                charts.render(var, rg, anom[vi], up[vi], lo[vi], nm, lat, lon, init=a.target, label=weekly.span_label(a.target, span),
                              out_path=path, clim_text=weekly.CLIM_TEXT_DAILY, alpha=charts.load_alpha_strict(name, rg, var, a.target),
                              calib_basis=charts.cfs_calib_texts(name, var, a.target)[0], alpha_scope="", extra_notes=dyn.NOTE[var])
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
    np.savez_compressed(os.path.join(clim.DATA, f"weekly_dyn_{a.target}.npz"), lat=lat, lon=lon, vars=NAMES,
                        **{f"{n}_{k}": v for n, d in summary.items() for k, v in d.items()})
    print(f"保存: data/weekly_dyn_{a.target}.npz")
    dist.write("cfs_week", a.target)


if __name__ == "__main__":
    main()
