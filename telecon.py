"""テレコネクション指数（PNA・WP・EU）の予報を作る。500hPa 高度の偏差から、Wallace and Gutzler (1981) の点の組み合わせ（格子点の線形結合）で求める簡易版。

  PNA = ¼[Z*(20°N,160°W) − Z*(45°N,165°W) + Z*(55°N,115°W) − Z*(30°N,85°W)]      太平洋・北米パターン
  WP  = ½[Z*(60°N,155°E) − Z*(30°N,155°E)]                                          西太平洋パターン
  EU  = −¼Z*(55°N,20°E) + ½Z*(55°N,75°E) − ¼Z*(40°N,145°E)                          ユーラシアパターン
  Z*: 500hPa 高度の偏差（gpm）。**この簡易版は、NOAA/CPC の回転 EOF による指数とは値が違う**（符号の意味は同じ）。
各期間（CFS 月平均 M1〜Q1・週平均 W1〜W4・CPS4 L1〜）について、予報のアンサンブル平均と各メンバー、気候値の分布（標準偏差・平均予報の位置［下から何%］・標準化値）を出す。
入力: CFS 月平均 data/cfs_monthly・CFS 日別 data/cfs_daily・CPS4（ローカル）data/c3s の z500。気候値は charts.py・weekly.py・cps4.py と同じ方法。
出力: output/telecon_{系列}_{初期日}.json（画面の「テレコネクション」ページが読む）。
使い方: python telecon.py --series cfs_month cfs_week --init 20261116   /   python telecon.py --series cps4 --init 20261101
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

import charts
import clim
import weekly

INDICES = {
    "PNA": dict(label="PNA（太平洋・北米パターン）", pts=[(20, -160, 0.25), (45, -165, -0.25), (55, -115, 0.25), (30, -85, -0.25)],
                note="正: アリューシャン付近（45°N・165°W）の高度が低く、北米西部（55°N・115°W）が高い。"),
    "WP": dict(label="WP（西太平洋パターン）", pts=[(60, 155, 0.5), (30, 155, -0.5)],
               note="正: 日本の北東（60°N・155°E）の高度が高く、日本の東（30°N・155°E）が低い。"),
    "EU": dict(label="EU（ユーラシアパターン）", pts=[(55, 20, -0.25), (55, 75, 0.5), (40, 145, -0.25)],
               note="正: 中央シベリア（55°N・75°E）の高度が高く、欧州北部（55°N・20°E）と日本付近（40°N・145°E）が低い。"),
}


def point_values(z, lat, lon, pts):
    """z[..., 緯, 経] から、各点（最寄りの格子）の値を [..., 点数] で返す。"""
    out = []
    for (la, lo, _) in pts:
        i = int(np.argmin(np.abs(lat - la)))
        j = int(np.argmin(np.abs(lon - (lo % 360))))
        out.append(z[..., i, j])
    return np.stack(out, axis=-1)


def combine(vals, pts):
    """点の値 [..., 点数] → 指数 [...]（重みの合計は0なので、気候値を引く前後で線形）。"""
    w = np.array([p[2] for p in pts])
    return (vals * w).sum(axis=-1)


def index_stats(name, clim_samples, members, off):
    """指数 name について。clim_samples[サンプル, 点]（期間平均済み）・members[メンバー, 点]・off[サンプル]。戻り値: dict(fc, members, sd, z, pct)。
    初期日のずれは、サンプルごとに回帰で補正してから気候値の平均・標準偏差を作る。"""
    pts = INDICES[name]["pts"]
    xa, _ = clim.adjust_offset(clim_samples, off)
    idx = combine(xa, pts)
    fc = combine(members, pts) - float(np.nanmean(idx))
    sd = float(np.nanstd(idx, ddof=1))
    mean_fc = float(np.nanmean(fc))
    return dict(fc=round(mean_fc, 1), members=[round(float(v), 1) for v in fc], sd=round(sd, 1),
                z=round(mean_fc / sd, 2) if sd > 0 else None, pct=round(float(((idx - np.nanmean(idx)) < mean_fc).mean() * 100)))


def run_cfs_month(init):
    x, off, yr, lat, lon = clim.load_samples(init, range(2019, 2026), 15)
    z = np.load(os.path.join(clim.CF_DIR, f"{init}.npz"))["arr"]
    z = z[[m for m in range(z.shape[0]) if not np.isnan(z[m]).all()]]
    zi = clim.VARS.index("z500")
    res = {}
    for p, leads in charts.PERIODS.items():
        xs = x[:, leads, zi].mean(axis=1)                         # [サンプル, 緯, 経]
        zs = z[:, leads, zi].mean(axis=1)
        res[p] = (charts.period_label(init, leads), xs, zs, off, lat, lon)
    return res


def run_cfs_week(init):
    x, off, yr, lat, lon = weekly.load_daily(init, range(2019, 2026), 7)
    z = np.load(os.path.join(weekly.DAILY, f"{init}.npz"))["arr"]
    z = z[[m for m in range(z.shape[0]) if not np.isnan(z[m]).all()]]
    zi = weekly.VARS.index("z500")
    res = {}
    for p, span in weekly.WEEKS.items():
        xs = x[:, span[0] - 1:span[1], zi].mean(axis=1)
        zs = z[:, span[0] - 1:span[1], zi].mean(axis=1)
        res[p] = (weekly.span_label(init, span), xs, zs, off, lat, lon)
    return res


def run_cps4(init):
    import cps4
    month = int(init[4:6])
    name = "geopotential"
    conv = cps4.VARS[name][1]
    F, lat, lon = cps4.load(os.path.join(cps4.C3S, f"jma_s4_{name}_monthly_mean_{init[:4]}-{month:02d}_L1-6.grib"), month)
    H, _, _ = cps4.load(os.path.join(cps4.C3S, f"jma_s4_{name}_monthly_mean_1993-2020-{month:02d}_L1-6.grib"), month)
    F, H = conv(F[0]), conv(H)
    periods = cps4.make_periods(month)
    res = {}
    for p in ("L1", "L2", "L3", "L4", "L2-4"):
        leads, label = periods[p]
        h = cps4.period_fields(H, leads).reshape(-1, *F.shape[2:])
        f = cps4.period_fields(F, leads)
        res[p] = (label, h, f, np.zeros(h.shape[0]), lat, lon)
    return res


def build(series, init):
    runner = {"cfs_month": run_cfs_month, "cfs_week": run_cfs_week, "cps4": run_cps4}[series]
    res = runner(init)
    out = {"series": series, "init": init, "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "indices": {k: dict(label=v["label"], note=v["note"], points=[dict(lat=p[0], lon=p[1], w=p[2]) for p in v["pts"]], periods={}) for k, v in INDICES.items()}}
    for p, (label, xs, zs, off, lat, lon) in res.items():
        pv_x = {k: point_values(xs, lat, lon, d["pts"]) for k, d in INDICES.items()}
        pv_z = {k: point_values(zs, lat, lon, d["pts"]) for k, d in INDICES.items()}
        for k in INDICES:
            st = index_stats(k, pv_x[k], pv_z[k], off)
            st["label"] = label
            out["indices"][k]["periods"][p] = st
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", nargs="+", required=True, choices=["cfs_month", "cfs_week", "cps4"])
    ap.add_argument("--init", required=True)
    a = ap.parse_args()
    for sid in a.series:
        d = build(sid, a.init)
        path = os.path.join(charts.OUT, f"telecon_{sid}_{a.init}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"{sid} {a.init}: テレコネクション指数 → {os.path.basename(path)}", flush=True)


if __name__ == "__main__":
    main()
