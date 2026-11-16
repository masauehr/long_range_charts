"""NOAA CFSv2（AWS noaa-cfs-pds）の time_grib（6時間毎）から、先頭30日の日平均を取得して 2.5° 格子で保存する。

L1（週平均の偏差・確率）用。変数は2m気温・降水・Z500の3つ。
- time_grib_NN/{変数}.NN.{初期日}00.daily.grb2 は6時間毎の記録（6,12,...時間後）。先頭120記録＝30日を
  .idx のバイト範囲1本で取り、4記録ずつ平均して日平均にする。
- 保存: data/cfs_daily/{初期日}.npz  arr[メンバー, 日(30), 変数(t2m,prate,z500), 緯度, 経度]（float32）
- 取得対象: 00Z の メンバー01〜04（週1〜4は4メンバーそろう）。
- 出典: NOAA/NCEP CFSv2（米政府データ。NOAAの推奨を示すものではない）。

使い方:
    python fetch_daily.py --target 20261112 --window 7      # 対象＋過去2019–2025の前後7日
    python fetch_daily.py --target 20261112 --years 2025 --window 0     # 小さな試験
    python fetch_daily.py --target 20261112 --lag-days 2                # ラグアンサンブル用（前2日の各サイクル）
"""
import argparse
import datetime as dt
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pygrib

import fetch_cfs

BASE = fetch_cfs.BASE
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cfs_daily")
VARS = [
    ("t2m", "tmp2m", lambda a: a - 273.15),       # ℃
    ("prate", "prate", lambda a: a * 86400.0),    # mm/day
    ("z500", "z500", lambda a: a),                # gpm
]
NDAY = 30
PER_DAY = 4                                       # 6時間毎
NREC = NDAY * PER_DAY
MEMBERS = [1, 2, 3, 4]
LAT, LON = fetch_cfs.LAT, fetch_cfs.LON


def make_regrid(lat, lon):
    """元格子→2.5°格子の双一次補間を、重みを前計算して返す（時間軸などの先頭次元は任意）。"""
    if lat[0] < lat[-1]:
        flip = True
        lat = lat[::-1]
    else:
        flip = False
    lon_ext = np.concatenate([lon, [360.0]])
    ly = np.interp(LAT, lat[::-1], np.arange(len(lat))[::-1])          # 元の行番号（小数）
    ly = np.clip(ly, 0, len(lat) - 1.000001)
    lx = np.interp(LON, lon_ext, np.arange(len(lon_ext)))
    y0, x0 = np.floor(ly).astype(int), np.floor(lx).astype(int)
    wy, wx = (ly - y0)[:, None], (lx - x0)[None, :]
    x1 = (x0 + 1) % len(lon)
    xx0 = x0 % len(lon)

    def f(a):
        if flip:
            a = a[..., ::-1, :]
        v00 = a[..., y0[:, None], xx0[None, :]]
        v01 = a[..., y0[:, None], x1[None, :]]
        v10 = a[..., (y0 + 1)[:, None], xx0[None, :]]
        v11 = a[..., (y0 + 1)[:, None], x1[None, :]]
        return (v00 * (1 - wy) * (1 - wx) + v01 * (1 - wy) * wx + v10 * wy * (1 - wx) + v11 * wy * wx).astype("float32")
    return f


def fetch_member(date, member, cycle=None):
    """1初期日・1メンバーの 30日×3変数の日平均（2.5°）を返す。取れない変数は NaN。cycle は 00/06/12/18。"""
    cycle = cycle or fetch_cfs.CYCLE
    out = np.full((NDAY, len(VARS), len(LAT), len(LON)), np.nan, dtype="float32")
    for vi, (_, name, conv) in enumerate(VARS):
        key = f"cfs.{date}/{cycle}/time_grib_{member:02d}/{name}.{member:02d}.{date}{cycle}.daily.grb2"
        try:
            idx = fetch_cfs.http(BASE + key + ".idx").decode().splitlines()
            if len(idx) <= NREC:
                continue                                    # 予報期間が短い
            offs = [int(line.split(":")[1]) for line in idx[:NREC + 1]]
            data = fetch_cfs.http(BASE + key, rng=f"bytes={offs[0]}-{offs[NREC] - 1}")
            arr = None
            for i in range(NREC):
                g = pygrib.fromstring(data[offs[i] - offs[0]:offs[i + 1] - offs[0]])
                if arr is None:
                    arr = np.empty((NREC,) + g.values.shape, dtype="float32")
                    lat, lon = g.latlons()
                    rg = make_regrid(lat[:, 0], lon[0, :])
                arr[i] = g.values
            daily = arr.reshape(NDAY, PER_DAY, *arr.shape[1:]).mean(1)
            out[:, vi] = conv(rg(daily))
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404):                    # 欠落（403/404）以外のサーバーエラーは再試行できるよう失敗として扱う
                raise
            print(f"  {date} メンバー{member} {name} 欠落: {e}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:   # 通信断。NaN で保存すると取り直されないので、呼び出し側へ投げる
            print(f"  {date} メンバー{member} {name} 通信失敗: {e}", file=sys.stderr)
            raise
        except Exception as e:                              # ファイルが読めない等（再試行しても直らない）は欠損として続ける
            print(f"  {date} メンバー{member} {name} 読めない: {e}", file=sys.stderr)
    return out


LAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cfs_daily_lag")
CYCLES = ["00", "06", "12", "18"]


def lag_inits(target, lag_days):
    """対象(00Z)より前の初期時刻（前 lag_days 日の各サイクル）。戻り値: [(日付, サイクル, メンバー群, 対象からのずれ日数)]。

    00Z はメンバー01〜04、06/12/18Z はメンバー01のみ（長さが違う。DATA_SOURCES.md）。ずれは負の日数（例: 前日18Z = -0.25）。
    """
    t = dt.datetime.strptime(target, "%Y%m%d")
    out = []
    for d in range(1, lag_days + 1):
        day = (t - dt.timedelta(days=d)).strftime("%Y%m%d")
        for cyc in CYCLES:
            out.append((day, cyc, MEMBERS if cyc == "00" else [1], -d + int(cyc) / 24.0))
    return out


def run_lag(target, lag_days, workers):
    """ラグ用の初期時刻を取得して data/cfs_daily_lag/{日付}{サイクル}.npz に保存する。"""
    ldir = os.path.join(LAG_DIR, target)                  # 対象日ごとに分ける（日付が変わると前の対象のラグが混ざらないように）
    os.makedirs(ldir, exist_ok=True)
    jobs = [j for j in lag_inits(target, lag_days) if not os.path.exists(os.path.join(ldir, f"{j[0]}{j[1]}.npz"))]
    print(f"ラグ用の初期時刻 {len(jobs)}件", flush=True)
    t0 = time.time()
    res = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_member, d, m, c): (d, c, m) for d, c, mem, _ in jobs for m in mem}
        for f in as_completed(futs):
            d, c, m = futs[f]
            res.setdefault((d, c), {})[m] = f.result()
    for d, c, mem, off in jobs:
        arr = np.stack([res[(d, c)][m] for m in mem])
        np.savez_compressed(os.path.join(ldir, f"{d}{c}.npz"), arr=arr, lat=LAT, lon=LON, off=off, members=mem,
                            vars=[v[0] for v in VARS])
        print(f"{d} {c}Z メンバー{mem} 保存 欠損率{np.isnan(arr).mean():.2%} 経過{time.time() - t0:.0f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag-days", type=int, default=0, help="対象より前の何日分の初期時刻をラグ用に取るか（0なら通常の取得）")
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.lag_days:
        run_lag(a.target, a.lag_days, a.workers)
        return
    y0, _, y1 = a.years.partition("-")
    years = range(int(y0), int(y1 or y0) + 1)
    os.makedirs(OUT_DIR, exist_ok=True)
    dates = fetch_cfs.analog_dates(a.target, years, a.window)
    todo = [d for d in dates if a.force or not os.path.exists(os.path.join(OUT_DIR, f"{d}.npz"))]
    print(f"対象 {len(dates)}日・未取得 {len(todo)}日", flush=True)
    t0 = time.time()
    res = {d: {} for d in todo}
    done = 0
    nodata = 0
    netfail = set()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_member, d, m): (d, m) for d in todo for m in MEMBERS}
        for f in as_completed(futs):
            d, m = futs[f]
            try:
                res[d][m] = f.result()
            except Exception:
                netfail.add(d)                              # この日は保存しない（再実行で取り直す）
                res[d][m] = None
            if len(res[d]) == len(MEMBERS) and d in netfail:
                continue
            if len(res[d]) == len(MEMBERS):
                arr = np.stack([res[d][k] for k in MEMBERS])
                res[d] = None
                if np.isnan(arr).all():
                    print(f"{d} データなし", file=sys.stderr)
                    nodata += 1
                else:
                    np.savez_compressed(os.path.join(OUT_DIR, f"{d}.npz"), arr=arr, lat=LAT, lon=LON,
                                        vars=[v[0] for v in VARS])
                    done += 1
                    print(f"[{done}/{len(todo)}] {d} 保存 欠損率{np.isnan(arr).mean():.2%} 経過{time.time() - t0:.0f}s", flush=True)
    if netfail:
        print(f"通信失敗 {len(netfail)}日（保存せず・再実行で取り直せる）", file=sys.stderr)
        sys.exit(1)
    if todo and nodata > len(todo) / 2:                     # 通信断などで大半が取れなかったら失敗として終える（自動手順が先へ進まないように）
        print(f"取得失敗: {nodata}/{len(todo)}日がデータなし", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
