"""CFSv2 運用予報の蓄積（fetch_cfs.py の出力）から、リード時間別のモデル気候値と三分位閾値を作る。

方法:
- 対象の初期日の前後 window 日 × 過去の年（既定 2019–2025）× 利用可能な全メンバーを1つの母集団とする。
- 初期日のずれ（日数）で対象期間もずれるため、グリッド点ごとに「値 ~ a + b×ずれ日数」を回帰し、
  ずれ0日（＝対象と同じ初期日）へ補正してから平均・標準偏差・三分位点を求める。
- 対象の予報は、同じ気候値からの偏差と、上位/下位三分位に入るメンバーの割合（確率）で表す。
- 検算（--check）: 年を1つ抜いて気候値を作り、抜いた年のサンプルが各三分位に入る割合が約1/3になるか確かめる。

出典: NOAA/NCEP CFSv2（米政府データ。NOAAの推奨を示すものではない）。気候値は運用予報の約7年分で、
気象庁の30年平年値や CFSv2 の再予報(1982-2010)とは異なる。
"""
import argparse
import datetime as dt
import glob
import os

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CF_DIR = os.path.join(DATA, "cfs_monthly")
VARS = ["t2m", "prate", "z500", "pot5"]


def load_samples(target, years, window, same_month=True):
    """気候値用のサンプルを読み込む。

    月平均ファイル(cfs_monthly)の「リードk」は**暦月**（初月は初期日以降の部分月）。対象と別の月の初期日を混ぜると
    リードが1か月ずれるため、same_month=True（既定）で対象と同じ月の初期日だけを使う。日別データ(cfs_daily)は
    初期日からの日数で揃っているので、same_month=False で前後の窓をすべて使える。

    戻り値: x[サンプル, リード, 変数, 緯度, 経度]（メンバーを展開済み, float32）、
            off[サンプル]（初期日のずれ日数）、yr[サンプル]（初期年）、lat, lon
    """
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    xs, offs, yrs = [], [], []
    lat = lon = None
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            if same_month and day.month != t.month:
                continue
            p = os.path.join(CF_DIR, day.strftime("%Y%m%d") + ".npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            a = z["arr"]                              # [メンバー, リード, 変数, 緯, 経]
            lat, lon = z["lat"], z["lon"]
            for m in range(a.shape[0]):
                if np.isnan(a[m]).all():
                    continue
                xs.append(a[m])
                offs.append(d)
                yrs.append(y)
    return np.stack(xs).astype("float32"), np.array(offs, float), np.array(yrs), lat, lon


def adjust_offset(x, off):
    """初期日のずれ(off)に対する回帰の傾きを引いて、ずれ0日の値へ補正する。

    x: [サンプル, ...]（NaN 可）。戻り値: 補正後の x, 傾き b（x と同じ後続形状）。
    """
    o = off.reshape((-1,) + (1,) * (x.ndim - 1))
    ok = ~np.isnan(x)
    n = ok.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        om = np.where(ok, o, 0).sum(0) / n
        xm = np.nansum(x, 0) / n
        do = np.where(ok, o - om, 0.0)
        dx = np.where(ok, x - xm, 0.0)
        b = (do * dx).sum(0) / (do * do).sum(0)
    b = np.where(np.isfinite(b), b, 0.0)
    return (x - b * o).astype("float32"), b.astype("float32")


def trend_adjust(x, yr, ref_year, lat):
    """全球平均の経年トレンド（変数・リードごとの1つの傾き）を使い、サンプルを ref_year の水準へ補正する。

    グリッド点ごとに傾きを求めると ENSO 等の年々変動を拾って不安定なため、全球平均の傾きだけを使う。
    x: [サンプル, リード, 変数, 緯, 経]。戻り値: 補正後の x, 傾き b[リード, 変数]（単位/年）。
    """
    w = np.cos(np.deg2rad(lat))[:, None]
    ok = ~np.isnan(x)
    gm = np.nansum(np.where(ok, x, 0) * w, axis=(-1, -2)) / np.maximum((ok * w).sum(axis=(-1, -2)), 1e-9)
    gm[~ok.any(axis=(-1, -2))] = np.nan
    years = np.array(sorted(set(yr)))
    ym = np.stack([np.nanmean(gm[yr == y], axis=0) for y in years])        # [年, リード, 変数]
    yc = years - years.mean()
    b = (yc[:, None, None] * (ym - ym.mean(0))).sum(0) / (yc ** 2).sum()
    shift = b[None] * (ref_year - yr)[:, None, None]
    return (x + shift[..., None, None]).astype("float32"), b.astype("float32")


def make_clim(x, off):
    """補正後サンプルから平均・標準偏差・三分位点（33.3/66.7%）・サンプル数を作る。"""
    xa, b = adjust_offset(x, off)
    return {
        "mean": np.nanmean(xa, 0).astype("float32"),
        "std": np.nanstd(xa, 0, ddof=1).astype("float32"),
        "t33": np.nanpercentile(xa, 100 / 3, axis=0).astype("float32"),
        "t67": np.nanpercentile(xa, 200 / 3, axis=0).astype("float32"),
        "n": (~np.isnan(xa)).sum(0).astype("int16"),
        "slope": b,
    }


def tercile_prob(members, clim):
    """メンバー集合 members[メンバー, ...] が上位/下位三分位に入る割合（NaN メンバーは除く）。"""
    ok = ~np.isnan(members)
    n = ok.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        up = ((members > clim["t67"]) & ok).sum(0) / n
        lo = ((members < clim["t33"]) & ok).sum(0) / n
    return up.astype("float32"), lo.astype("float32"), n


def check(x, off, yr, lat=None, detrend=False):
    """年を1つ抜いた検算。抜いた年のサンプルが上位/下位三分位に入る割合（全球・変数/リード別の平均）を返す。

    detrend=True なら、抜いた年以外から全球平均トレンドを求めて、抜いた年の水準へ補正してから気候値を作る。
    """
    res = []
    for y in sorted(set(yr)):
        tr = yr != y
        xt = x[tr]
        if detrend:
            xt, _ = trend_adjust(xt, yr[tr], y, lat)
        c = make_clim(xt, off[tr])
        te = (yr == y) & (off == 0)
        if not te.any():
            continue
        up, lo, _ = tercile_prob(x[te], c)
        res.append((y, np.nanmean(up, axis=(2, 3)), np.nanmean(lo, axis=(2, 3))))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--check", action="store_true", help="年を1つ抜く検算を表示")
    ap.add_argument("--detrend", action="store_true", help="全球平均の経年トレンドを対象年の水準へ補正する")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    years = range(int(y0), int(y1 or y0) + 1)
    x, off, yr, lat, lon = load_samples(a.target, years, a.window)
    print(f"サンプル {len(x)}（初期日×メンバー）, 年 {sorted(set(yr))}")
    x0 = x
    if a.detrend:
        x, b = trend_adjust(x, yr, int(a.target[:4]), lat)
        print("トレンド補正: 全球平均の傾き(リード0〜3・t2m,prate,z500,pot5)/年\n", np.round(b[:4], 3))
    c = make_clim(x, off)
    np.savez_compressed(os.path.join(DATA, f"clim_{a.target[4:]}.npz"), lat=lat, lon=lon, vars=VARS, **c)
    # 対象の予報
    z = np.load(os.path.join(CF_DIR, f"{a.target}.npz"))["arr"]
    up, lo, n = tercile_prob(z, c)
    anom = np.nanmean(z, 0) - c["mean"]
    np.savez_compressed(os.path.join(DATA, f"prob_{a.target}.npz"), lat=lat, lon=lon, vars=VARS,
                        anom=anom.astype("float32"), p_upper=up, p_lower=lo, n_members=n.astype("int16"))
    print(f"保存: data/clim_{a.target[4:]}.npz, data/prob_{a.target}.npz")
    if a.check:
        print("年抜き検算（上位/下位三分位に入る割合の全球平均。理想は 0.333）")
        for dt_ in (False, True):
            r = check(x0, off, yr, lat, detrend=dt_)
            # 指標: 各年・リード0〜3・変数ごとの |割合-1/3| の平均（小さいほど良い。年ごとのぶれを見る）
            dev = np.array([[np.abs(q[1][:4] - 1 / 3), np.abs(q[2][:4] - 1 / 3)] for q in r])   # [年, 上下, リード, 変数]
            print(f"--- トレンド補正{'あり' if dt_ else 'なし'}: |割合-1/3| の平均（リード0〜3, 年7つ）  [t2m, prate, z500, pot5]")
            print("  全体", np.round(dev.mean((0, 1, 2)), 4))
            for yy, d in zip([q[0] for q in r], dev):
                print(" ", yy, np.round(d.mean((0, 1)), 3))


if __name__ == "__main__":
    main()
