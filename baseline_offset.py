"""気候値の基準の違い（気象庁の平年 1991–2020 と、本図の気候値 2019–2025）を再解析から見積もる。

NCEP/NCAR 再解析（NOAA PSL）の2m気温で、同じ期間（既定 11/14〜12/11 の28日）について
  オフセット = （2019–2025 の各年平均）−（1991–2020 の日別長期平均の同期間平均）
を地域の代表点で求める。これを CFSv2 の偏差（気候値比）に足すと、気象庁の平年比に近い量になる。
ただし CFSv2 の気候値はモデル自身の気候値なので、足し合わせは近似（モデルのバイアスは別）。

データ: https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis/ （日別）と ncep.reanalysis.derived/surface_gauss/（平年）。
  Kalnay et al. 1996。NOAA PSL のデータ。NOAAの推奨を示すものではない。
使い方: python baseline_offset.py --ref reference/jma_1month_20261111.json
"""
import argparse
import datetime as dt
import json
import os
import urllib.request

import numpy as np
import xarray as xr

import clim

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


def offsets(points, start_md, days, years):
    """地域の代表点ごとに、同期間の「年平均−1991–2020平年」を返す。{地域: (平均, 最小, 最大)}"""
    m0, d0 = map(int, start_md.split("-"))
    ltm = xr.open_dataset(fetch(LTM, "air.2m.gauss.day.ltm.1991-2020.nc"))["air"]
    i0 = noleap_index(m0, d0)
    ltm_sel = ltm.isel(time=slice(i0, i0 + days))
    cl = {}
    for y in years:
        ds = xr.open_dataset(fetch(f"{PSL}/ncep.reanalysis.dailyavgs/surface_gauss/air.2m.gauss.{y}.nc",
                                   f"air.2m.gauss.{y}.nc"))["air"]
        t = ds["time"].values.astype("datetime64[D]")
        s0 = np.datetime64(f"{y}-{m0:02d}-{d0:02d}")
        sel = ds.isel(time=np.where((t >= s0) & (t < s0 + days))[0])
        assert sel.sizes["time"] == days, (y, sel.sizes)
        cl[y] = sel
    out = {}
    for name, pt in points.items():
        norm = point_series(ltm_sel, pt).mean()
        per = np.array([point_series(cl[y], pt).mean() - norm for y in years])
        out[name] = (float(per.mean()), float(per.min()), float(per.max()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--years", default="2019-2025")
    a = ap.parse_args()
    ref = json.load(open(a.ref, encoding="utf-8"))
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    pts = {n: d["点"] for n, d in ref["地域"].items()}
    print("再解析T2mの「2019–2025平均−1991–2020平年」（平均 [年ごとの範囲]）")
    print("| 期間 | " + " | ".join(pts) + " |")
    print("|---|" + "---|" * len(pts))
    for k, w in ref["期間"].items():
        o = offsets(pts, w["開始"], w["日数"], years)
        print(f"| {k}（{w['開始']}から{w['日数']}日） | " + " | ".join(f"{v[0]:+.2f} [{v[1]:+.1f}〜{v[2]:+.1f}]" for v in o.values()) + " |")


if __name__ == "__main__":
    main()
