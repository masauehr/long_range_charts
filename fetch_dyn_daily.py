"""NOAA CFSv2 の日別データ（time_grib）から、力学診断の量（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の30日分の日平均を取得する（週平均の図用）。

CFSv2 の日別ファイルには、NOAA が計算した流線関数（STRM）・速度ポテンシャル（VPOT）・OLR（ULWRF 大気上端）が最初から入っている（6時間毎・
fetch_daily.py と同じ取り方: 索引のバイト範囲・6時間値を日平均・2.5°へ補間）。ψ・χ は 10⁶ m²/s にし、全球平均0にそろえる（月平均の力学診断・気象庁の図と同じ規約）。
保存: data/cfs_dyn_daily/{初期日}.npz  arr[メンバー(4), 日(30), 変数(4), 緯(73), 経(144)]  変数 = psi850, psi200, chi200, olr
使い方: python fetch_dyn_daily.py --target 20261116 [--workers 16]    # 対象の初期日と、過去（2019–2025）の前後7日の初期日
"""
import argparse
import os
import sys
import time
import urllib.error
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pygrib

import dyn_solver
import fetch_cfs
import fetch_daily

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cfs_dyn_daily")
NAMES = ["psi850", "psi200", "chi200", "olr"]
SOURCES = [("psi850", "psi850", 1e-6), ("psi200", "psi200", 1e-6), ("chi200", "chi200", 1e-6), ("olr", "ulwtoa", 1.0)]
NDAY, PER_DAY = fetch_daily.NDAY, fetch_daily.PER_DAY
NREC = NDAY * PER_DAY
MEMBERS = fetch_daily.MEMBERS
LAT, LON = fetch_cfs.LAT, fetch_cfs.LON


def fetch_member(date, member):
    """1初期日・1メンバーの 30日×4変数の日平均（2.5°）。取れない変数は NaN。通信エラーは投げる（保存せず再実行で取り直す）。"""
    out = np.full((NDAY, len(SOURCES), len(LAT), len(LON)), np.nan, dtype="float32")
    cycle = fetch_cfs.CYCLE
    for vi, (_, name, scale) in enumerate(SOURCES):
        key = f"cfs.{date}/{cycle}/time_grib_{member:02d}/{name}.{member:02d}.{date}{cycle}.daily.grb2"
        try:
            idx = fetch_cfs.http(fetch_cfs.BASE + key + ".idx").decode().splitlines()
            if len(idx) <= NREC:
                continue
            offs = [int(line.split(":")[1]) for line in idx[:NREC + 1]]
            data = fetch_cfs.http(fetch_cfs.BASE + key, rng=f"bytes={offs[0]}-{offs[NREC] - 1}")
            arr, rg = None, None
            for i in range(NREC):
                g = pygrib.fromstring(data[offs[i] - offs[0]:offs[i + 1] - offs[0]])
                if arr is None:
                    arr = np.empty((NREC,) + g.values.shape, dtype="float32")
                    lat, lon = g.latlons()
                    rg = fetch_daily.make_regrid(lat[:, 0], lon[0, :])
                arr[i] = g.values
            daily = arr.reshape(NDAY, PER_DAY, *arr.shape[1:]).mean(1)
            out[:, vi] = rg(daily) * scale
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404):
                raise
            print(f"  {date} メンバー{member} {name} 欠落: {e}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"  {date} メンバー{member} {name} 通信失敗: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"  {date} メンバー{member} {name} 読めない: {e}", file=sys.stderr)
    for vi in range(3):                                   # ψ・χ は全球平均0にそろえる
        out[:, vi] = dyn_solver.remove_global_mean(out[:, vi], LAT)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    os.makedirs(OUT_DIR, exist_ok=True)
    dates = fetch_cfs.analog_dates(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    todo = [d for d in dates if a.force or not os.path.exists(os.path.join(OUT_DIR, f"{d}.npz"))]
    print(f"対象 {len(dates)}日・未取得 {len(todo)}日", flush=True)
    t0 = time.time()
    res = {d: {} for d in todo}
    netfail, nodata, done = set(), 0, 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_member, d, m): (d, m) for d in todo for m in MEMBERS}
        for f in as_completed(futs):
            d, m = futs[f]
            try:
                res[d][m] = f.result()
            except Exception:
                netfail.add(d)
                res[d][m] = None
            if len(res[d]) == len(MEMBERS) and d not in netfail:
                arr = np.stack([res[d][k] for k in MEMBERS])
                res[d] = None
                if np.isnan(arr).all():
                    print(f"{d} データなし", file=sys.stderr)
                    if d not in fetch_cfs.KNOWN_BAD:
                        nodata += 1
                    continue
                outp = os.path.join(OUT_DIR, f"{d}.npz")
                np.savez_compressed(outp + ".tmp.npz", arr=arr, lat=LAT, lon=LON, vars=NAMES)
                os.replace(outp + ".tmp.npz", outp)
                done += 1
                print(f"[{done}/{len(todo)}] {d} 保存 欠損率{np.isnan(arr).mean():.2%} 経過{time.time() - t0:.0f}s", flush=True)
    if netfail:
        print(f"通信失敗 {len(netfail)}日（保存せず・再実行で取り直せる）", file=sys.stderr)
        sys.exit(1)
    if todo and nodata > len(todo) / 2:
        print(f"取得失敗: {nodata}/{len(todo)}日がデータなし", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
