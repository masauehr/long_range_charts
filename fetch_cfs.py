"""NOAA CFSv2（AWS noaa-cfs-pds）の月平均予報から必要な変数だけを取得して 2.5° 格子で保存する。

- .idx のバイト範囲指定で、2m気温・降水・Z500・海洋5m水温の4変数だけを取る（1ファイル約0.24MB）。
- 保存形式: data/cfs_monthly/{初期日}.npz
    arr[メンバー, リード月, 変数, 緯度, 経度]（float32・2.5°・北→南・0〜357.5E）
- 出典: NOAA/NCEP CFSv2（米政府データ。NOAAの推奨を示すものではない）。

使い方:
    python fetch_cfs.py --target 20261112              # 対象の初期値＋過去の同時期（前後15日）
    python fetch_cfs.py --target 20261112 --years 2025 --window 2 --leads 3   # 小さな試験
"""
import argparse
import datetime as dt
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygrib
from scipy.interpolate import RegularGridInterpolator

BASE = "https://noaa-cfs-pds.s3.amazonaws.com/"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cfs_monthly")
# 取得する変数: (名前, ファイル種別, idx内の検索パターン, 単位変換)
VARS = [
    ("t2m", "flxf", r":TMP:2 m above ground:", lambda a: a - 273.15),     # ℃
    ("prate", "flxf", r":PRATE:surface:", lambda a: a * 86400.0),         # mm/day
    ("z500", "pgbf", r":HGT:500 mb:", lambda a: a),                       # gpm
    ("pot5", "ocnf", r":POT:5 m below sea level:", lambda a: a - 273.15), # ℃（SSTの代わり）
]
LAT = np.arange(90, -90.1, -2.5)    # 北→南 73点
LON = np.arange(0, 360, 2.5)        # 144点
MEMBERS = [1, 2, 3, 4]
CYCLE = "00"


def http(url, rng=None, retry=4):
    """HTTP取得（再試行つき）。"""
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"Range": rng} if rng else {})
            return urllib.request.urlopen(req, timeout=60).read()
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(1.5 * (i + 1))


def list_month_files(date, member):
    """初期日・メンバーの月平均ファイルを種別ごとに月順で返す。"""
    prefix = f"cfs.{date}/{CYCLE}/monthly_grib_{member:02d}/"
    keys = []
    token = None
    while True:
        url = f"{BASE}?list-type=2&prefix={prefix}&max-keys=1000"
        if token:
            url += f"&continuation-token={token}"
        root = ET.fromstring(http(url))
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys += [e.find("s:Key", ns).text for e in root.findall("s:Contents", ns)]
        t = root.find("s:NextContinuationToken", ns)
        if t is None:
            break
        token = t.text
    # 時刻別（00Z等）を除いた、メンバー平均なしの「.avrg.grib.grb2」だけ
    keys = [k for k in keys if re.search(r"\.avrg\.grib\.grb2$", k)]
    out = {}
    for k in keys:
        name = k.split("/")[-1]
        out.setdefault(name.split(".")[0], []).append(k)
    return {kind: sorted(v) for kind, v in out.items()}


def to_grid(msg, conv):
    """GRIBメッセージを 2.5° 格子へ補間して返す。"""
    # 海洋変数は陸が欠測（マスク）。NaN にして補間に混ざらないようにする
    vals = np.ma.filled(np.ma.masked_greater(msg.values, 1e15).astype("float64"), np.nan)
    lats, lons = msg.latlons()
    la = lats[:, 0]
    lo = lons[0, :]
    if la[0] < la[-1]:               # 南→北なら反転
        la = la[::-1]
        vals = vals[::-1, :]
    # 経度の巻き込み用に東端へ360度を足す
    vals = np.concatenate([vals, vals[:, :1]], axis=1)
    lo = np.concatenate([lo, [360.0]])
    f = RegularGridInterpolator((la[::-1], lo), vals[::-1, :], bounds_error=False, fill_value=None)
    yy, xx = np.meshgrid(LAT, LON, indexing="ij")
    return conv(f((yy, xx))).astype("float32")


def fetch_file(key, patterns):
    """1ファイルから指定パターンのレコードだけを取って [msg] を返す。"""
    idx = http(BASE + key + ".idx").decode().splitlines()
    offs = [int(line.split(":")[1]) for line in idx]
    got = {}
    for pat, _ in patterns:
        for i, line in enumerate(idx):
            if re.search(pat, line):
                end = f"{offs[i + 1] - 1}" if i + 1 < len(offs) else ""
                data = http(BASE + key, rng=f"bytes={offs[i]}-{end}")
                got[pat] = pygrib.fromstring(data)
                break
    return got


def fetch_init(date, leads):
    """1初期日分（4メンバー×リード月×4変数）を取得して配列にする。"""
    arr = np.full((len(MEMBERS), leads, len(VARS), len(LAT), len(LON)), np.nan, dtype="float32")
    tasks = []
    for mi, m in enumerate(MEMBERS):
        files = list_month_files(date, m)
        for vi, (_, kind, pat, conv) in enumerate(VARS):
            for li, key in enumerate(files.get(kind, [])[:leads]):
                tasks.append((mi, li, vi, key, pat, conv))

    def run(t):
        mi, li, vi, key, pat, conv = t
        msg = fetch_file(key, [(pat, None)]).get(pat)
        if msg is not None:
            arr[mi, li, vi] = to_grid(msg, conv)

    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(run, tasks))
    return arr


def analog_dates(target, years, window):
    """対象の初期日と、過去の同時期（前後 window 日）の初期日リストを返す。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    out = [t]
    for y in years:
        c = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            out.append(c + dt.timedelta(days=d))
    return [d.strftime("%Y%m%d") for d in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="対象の初期日 YYYYMMDD（00Z）")
    ap.add_argument("--years", default="2019-2025", help="過去年の範囲（例 2019-2025 または 2025）")
    ap.add_argument("--window", type=int, default=15, help="前後の日数")
    ap.add_argument("--force", action="store_true", help="既存ファイルも取り直す")
    ap.add_argument("--leads", type=int, default=7, help="取得するリード月の数")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    years = range(int(y0), int(y1 or y0) + 1)
    os.makedirs(OUT_DIR, exist_ok=True)
    dates = analog_dates(a.target, years, a.window)
    t0 = time.time()
    for i, d in enumerate(dates):
        path = os.path.join(OUT_DIR, f"{d}.npz")
        if os.path.exists(path) and not a.force:
            continue
        try:
            arr = fetch_init(d, a.leads)
        except Exception as e:      # 欠落日などは飛ばして続ける
            print(f"[{i + 1}/{len(dates)}] {d} 失敗: {e}", file=sys.stderr)
            continue
        if np.isnan(arr).all():
            print(f"[{i + 1}/{len(dates)}] {d} データなし", file=sys.stderr)
            continue
        np.savez_compressed(path, arr=arr, lat=LAT, lon=LON, vars=[v[0] for v in VARS])
        print(f"[{i + 1}/{len(dates)}] {d} 保存 欠損率{np.isnan(arr).mean():.2%} 経過{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
