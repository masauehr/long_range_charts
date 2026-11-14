"""気候値の基準の違い（気象庁の平年 1991–2020 と、本図の気候値 2019–2025）を再解析から見積もる。

NCEP/NCAR 再解析（NOAA PSL）の2m気温で、同じ期間（既定 11/14〜12/11 の28日）について
  オフセット = （2019–2025 の各年平均）−（1991–2020 の日別長期平均の同期間平均）
を地域の代表点で求める。これを CFSv2 の偏差（気候値比）に足すと、気象庁の平年比に近い量になる。
ただし CFSv2 の気候値はモデル自身の気候値なので、足し合わせは近似（モデルのバイアスは別）。

データ: https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis/ （日別）と ncep.reanalysis.derived/surface_gauss/（平年）。
  Kalnay et al. 1996。NOAA PSL のデータ。NOAAの推奨を示すものではない。
使い方: python baseline_offset.py --ref reference/jma_1month_20261111.json --target 20261112
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

import numpy as np
import xarray as xr

import clim
from compare_jma import at_point

PSL = "https://downloads.psl.noaa.gov/Datasets"
D_DIR = os.path.join(clim.DATA, "ref_psl")
LTM = f"{PSL}/ncep.reanalysis.derived/surface_gauss/air.2m.gauss.day.ltm.1991-2020.nc"


def fetch(url, name):
    """未取得ならダウンロードする（urllib）。"""
    os.makedirs(D_DIR, exist_ok=True)
    p = os.path.join(D_DIR, name)
    if not os.path.exists(p):
        with urllib.request.urlopen(url, timeout=120) as r, open(p, "wb") as f:
            f.write(r.read())
    return p


def noleap_index(month, day):
    """うるう日なし365日の通日インデックス（0始まり）。"""
    return (dt.date(2001, month, day) - dt.date(2001, 1, 1)).days


def point_series(da, pt):
    lat = da["lat"].values
    lon = da["lon"].values
    arr = da.values
    if lat[0] < lat[-1]:
        lat, arr = lat[::-1], arr[:, ::-1, :]
    from scipy.interpolate import RegularGridInterpolator
    arr = np.concatenate([arr, arr[:, :, :1]], axis=2)
    lo = np.concatenate([lon, [360.0]])
    f = RegularGridInterpolator((np.arange(arr.shape[0]), lat[::-1], lo), arr[:, ::-1, :], bounds_error=False)
    n = arr.shape[0]
    return np.array([float(f((i, pt[0], pt[1]))) for i in range(n)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--start", default="11-14", help="期間の開始 MM-DD（気象庁の対象期間）")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--years", default="2019-2025")
    a = ap.parse_args()
    ref = json.load(open(a.ref, encoding="utf-8"))
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    m0, d0 = map(int, a.start.split("-"))
    ltm = xr.open_dataset(fetch(LTM, "air.2m.gauss.day.ltm.1991-2020.nc"))["air"]
    i0 = noleap_index(m0, d0)
    ltm_sel = ltm.isel(time=slice(i0, i0 + a.days))
    cl = {}
    for y in years:
        ds = xr.open_dataset(fetch(f"{PSL}/ncep.reanalysis.dailyavgs/surface_gauss/air.2m.gauss.{y}.nc",
                                   f"air.2m.gauss.{y}.nc"))["air"]
        t = ds["time"].values.astype("datetime64[D]")
        s = np.datetime64(f"{y}-{m0:02d}-{d0:02d}")
        sel = ds.isel(time=np.where((t >= s) & (t < s + a.days))[0])
        cl[y] = sel
        assert sel.sizes["time"] == a.days, (y, sel.sizes)
    # CFS の偏差（compare_jma と同じ代表点・ブロック0）
    c = np.load(os.path.join(clim.DATA, f"clim_{a.target[4:]}.npz"))
    z = np.load(os.path.join(clim.CF_DIR, f"{a.target}.npz"))["arr"][:, 0, 0]
    mean = c["mean"][0, 0]
    print(f"期間 {a.start} から{a.days}日・再解析T2m（K→℃の差）。オフセット=2019–2025平均−1991–2020平年")
    print("| 地域 | 気象庁 平年差 | CFS 偏差(2019–25比) | 再解析オフセット(2019–25−1991–2020) | 年ごとの範囲 | CFS偏差+オフセット |")
    print("|---|---|---|---|---|---|")
    for name, d in ref["地域"].items():
        pt = d["点"]
        norm = point_series(ltm_sel, pt).mean()
        per = np.array([point_series(cl[y], pt).mean() - norm for y in years])
        cfs = float(np.mean(at_point(z, c["lat"], c["lon"], pt)) - at_point(mean, c["lat"], c["lon"], pt))
        print(f"| {name} | {d['平年差']:+.1f}℃ | {cfs:+.1f}℃ | {per.mean():+.2f}℃ | {per.min():+.1f}〜{per.max():+.1f} | {cfs + per.mean():+.1f}℃ |")


if __name__ == "__main__":
    main()
