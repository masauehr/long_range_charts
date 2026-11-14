"""L1 図（週平均の偏差と三分位確率）と、気象庁の1か月予報の期間に合わせた集計。

日別データ（fetch_daily.py の出力 data/cfs_daily/）から、初期日からの日数で揃えた窓の平均を作る。
  W1〜W4: 予報1〜7日目, 8〜14, 15〜21, 22〜28（初期日=1日目）
  気象庁の1か月予報に合わせた窓（初期日11/12・気象庁の対象期間11/14〜）: 日3〜9, 10〜16, 17〜30, 3〜30
気候値は 2019–2025 年の前後 window 日の初期日（日数で揃うので月をまたいでよい）。メンバーは00Zの4つ。

使い方:
    python weekly.py --target 20261112
"""
import argparse
import datetime as dt
import glob
import os

import numpy as np

import charts
import clim

DAILY = os.path.join(clim.DATA, "cfs_daily")
LAG_DIR = os.path.join(clim.DATA, "cfs_daily_lag")
VARS = ["t2m", "prate", "z500"]
# 窓: 名前 -> (開始日, 終了日)（初期日=1日目, 両端含む）
WEEKS = {"W1": (1, 7), "W2": (8, 14), "W3": (15, 21), "W4": (22, 28)}
JMA_WINDOWS = {"J1": (3, 9), "J2": (10, 16), "J34": (17, 30), "J28": (3, 30)}
CLIM_TEXT_DAILY = "CFSv2の運用予報 2019–2025年の前後7日の初期日（初期日からの日数で揃え、ずれを補正）・約7年"


def load_daily(target, years, window):
    """日別サンプル x[サンプル, 日, 変数, 緯, 経]・初期日のずれ・年を返す（メンバー展開済み）。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    xs, offs, yrs = [], [], []
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            p = os.path.join(DAILY, day.strftime("%Y%m%d") + ".npz")
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


def load_lag(target):
    """ラグ用の初期時刻を読む。戻り値: (配列のリスト[メンバー,日,変数,緯,経], 各ずれ日数のリスト)。"""
    arrs, offs = [], []
    for p in sorted(glob.glob(os.path.join(LAG_DIR, "*.npz"))):
        z = np.load(p)
        for m in range(z["arr"].shape[0]):
            arrs.append(z["arr"][m])
            offs.append(float(z["off"]))
    return arrs, offs


def window_stats(x, off, z, span, lag=None):
    """窓 span=(開始日,終了日) の平均を作り、気候値・対象の偏差・確率を返す。

    lag=(配列リスト, ずれ日数リスト) があれば、ラグメンバーを加える。ラグメンバーは「初期日が off 日ずれたサンプル」と
    同じ扱いで、気候値と同じ傾き（初期日のずれ回帰）を使って対象の初期日の水準へ補正してから混ぜる。
    """
    a, b = span
    xp = x[:, a - 1:b].mean(axis=1)             # [サンプル, 変数, 緯, 経]
    zp = z[:, a - 1:b].mean(axis=1)             # [メンバー, 変数, 緯, 経]
    c = clim.make_clim(xp, off)
    if lag:
        extra = np.stack([arr[a - 1:b].mean(axis=0) - c["slope"] * o for arr, o in zip(*lag)])
        zp = np.concatenate([zp, extra.astype("float32")], axis=0)
    up, lo, n = clim.tercile_prob(zp, c)
    return c, np.nanmean(zp, 0) - c["mean"], up, lo, zp


def span_label(init, span):
    d0 = dt.datetime.strptime(init, "%Y%m%d").date()
    s, e = d0 + dt.timedelta(days=span[0] - 1), d0 + dt.timedelta(days=span[1] - 1)
    return f"予報{span[0]}〜{span[1]}日目（{s.month}/{s.day}〜{e.month}/{e.day}）の平均"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    ap.add_argument("--vars", nargs="*", default=VARS)
    ap.add_argument("--weeks", nargs="*", default=list(WEEKS))
    ap.add_argument("--lagged", action="store_true", help="ラグアンサンブル（data/cfs_daily_lag の初期時刻を加える）")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    x, off, yr, lat, lon = load_daily(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    print(f"サンプル {len(x)}（初期日×メンバー）", flush=True)
    z = np.load(os.path.join(DAILY, f"{a.target}.npz"))["arr"]
    nm = int(z.shape[0])
    lag = load_lag(a.target) if a.lagged else None
    suffix = "_lag" if a.lagged else ""
    member_text = None
    if lag:
        nl = len(lag[0])
        member_text = (f"メンバー{nm + nl}（00Z {nm}＋前日以前の各サイクル{nl}。初期日のずれは気候値と同じ傾きで補正）。"
                       f"週1は古い初期値の分だけ精度が落ちうる。")
    summary = {}
    for name, span in {**WEEKS, **JMA_WINDOWS}.items():
        c, anom, up, lo, zp = window_stats(x, off, z, span, lag)
        summary[name] = dict(span=span, anom=anom, p_upper=up, p_lower=lo, members=zp, mean=c["mean"], t67=c["t67"],
                             t33=c["t33"])
        if name in a.weeks:
            for var in a.vars:
                vi = VARS.index(var)
                for rg in a.regions:
                    path = os.path.join(charts.OUT, f"cfsv2_{a.target}_{var}_{name}_{rg}{suffix}.png")
                    charts.render(var, rg, anom[vi], up[vi], lo[vi], nm, lat, lon, init=a.target,
                                  label=span_label(a.target, span), out_path=path, clim_text=CLIM_TEXT_DAILY,
                                  member_text=member_text, alpha=charts.load_alpha(name, rg, var),
                                  calib_basis=charts.cfs_calib_texts(name, var)[0],
                                  alpha_scope=charts.cfs_calib_texts(name, var)[1])
                    print("出力", os.path.relpath(path, clim.ROOT), flush=True)
    np.savez_compressed(os.path.join(clim.DATA, f"weekly_{a.target}{suffix}.npz"), lat=lat, lon=lon, vars=VARS,
                        **{f"{n}_{k}": v for n, d in summary.items() for k, v in d.items() if k != "span"})
    print(f"保存: data/weekly_{a.target}{suffix}.npz")


if __name__ == "__main__":
    main()
