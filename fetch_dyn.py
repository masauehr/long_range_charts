"""NOAA CFSv2 の月平均から、力学診断用の量（流線関数・速度ポテンシャル・OLR）を作って保存する。

取得: 850・200hPa の風（u・v）と、大気上端の上向き長波放射（OLR）。索引（.idx）で必要なレコードだけをバイト範囲で取る（fetch_cfs と同じ）。
  - u と v は GRIB の1つのまとまり（2フィールド）に入っているので、そのまま範囲で取り、一時ファイル経由で pygrib で読む。
導出: 風を 2.5° 格子へ補間し、dyn_solver で ψ850・ψ200・χ200 を求める（単位 10⁶ m²/s）。OLR は W/m²。
保存: data/cfs_dyn/{初期日}.npz  arr[メンバー(4), リード(0〜3), 変数(4), 緯(73), 経(144)]  変数 = psi850, psi200, chi200, olr
  対象月と同じ月の初期日だけを取る（月平均のリードは暦月のため。fetch_cfs と同じ考え方）。

使い方: python fetch_dyn.py --target 20261116     # 対象の初期日と、過去（2019–2025）の同じ月の前後15日の初期日
"""
import argparse
import datetime as dt
import os
import re
import sys
import tempfile
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygrib

import dyn_solver
import fetch_cfs

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cfs_dyn")
NAMES = ["psi850", "psi200", "chi200", "olr"]
LEADS = 4
SCALE = 1e-6                                   # ψ・χ を 10⁶ m²/s にする


def _range_for(idx, offs, pat):
    """索引の行 pat から、そのまとまり（u・v のように同じ位置に並ぶ行を含む）のバイト範囲を返す。"""
    for i, line in enumerate(idx):
        if re.search(pat, line):
            j = i
            while j < len(idx) and offs[j] == offs[i]:
                j += 1
            end = f"{offs[j] - 1}" if j < len(idx) else ""
            return f"bytes={offs[i]}-{end}"
    return None


def _read_messages(data):
    """GRIB のバイト列を一時ファイル経由で読み、{shortName: msg} を返す。"""
    tf = tempfile.NamedTemporaryFile(suffix=".grb2", delete=False)
    try:
        tf.write(data)
        tf.close()
        out = {}
        g = pygrib.open(tf.name)
        for m in g:
            out[m.shortName] = (m.values.copy(), m.latlons())
        g.close()
        return out
    finally:
        os.unlink(tf.name)


def _grid(values, latlon):
    """pygrib の値と緯度経度を、fetch_cfs.to_grid が期待する形（msg 風）で 2.5° 格子へ補間する。"""
    class M:  # noqa: N801
        pass
    m = M()
    m.values = values
    m.latlons = lambda: latlon
    return fetch_cfs.to_grid(m, lambda a: a)


def fetch_member_lead(pg_key, fl_key):
    """1メンバー・1リードの (u850, v850, u200, v200, olr)（2.5°）。取れない量は NaN。"""
    nan = np.full((len(fetch_cfs.LAT), len(fetch_cfs.LON)), np.nan, dtype="float32")
    res = {k: nan for k in ("u850", "v850", "u200", "v200", "olr")}
    idx = fetch_cfs.http(fetch_cfs.BASE + pg_key + ".idx").decode().splitlines()
    offs = [int(line.split(":")[1]) for line in idx]
    for lev in (850, 200):
        rng = _range_for(idx, offs, rf":UGRD:{lev} mb:")
        if rng is None:
            continue
        try:
            msgs = _read_messages(fetch_cfs.http(fetch_cfs.BASE + pg_key, rng=rng))
        except urllib.error.URLError:
            raise
        except Exception:
            continue                                   # 読めない（欠けている）ものは NaN
        for short, name in (("avg_u", f"u{lev}"), ("avg_v", f"v{lev}")):
            if short in msgs:
                res[name] = _grid(*msgs[short])
    idx2 = fetch_cfs.http(fetch_cfs.BASE + fl_key + ".idx").decode().splitlines()
    offs2 = [int(line.split(":")[1]) for line in idx2]
    rng = _range_for(idx2, offs2, r":ULWRF:top of atmosphere:")
    if rng is not None:
        try:
            msgs = _read_messages(fetch_cfs.http(fetch_cfs.BASE + fl_key, rng=rng))
            for v in msgs.values():
                res["olr"] = _grid(*v)
                break
        except urllib.error.URLError:
            raise
        except Exception:
            pass
    return res


def fetch_init(date):
    """1初期日（4メンバー×4リード）の導出量 arr[メンバー, リード, 4, 緯, 経] を作る。"""
    n_m = len(fetch_cfs.MEMBERS)
    raw = {k: np.full((n_m, LEADS) + (len(fetch_cfs.LAT), len(fetch_cfs.LON)), np.nan, dtype="float32") for k in ("u850", "v850", "u200", "v200", "olr")}
    tasks = []
    for mi, m in enumerate(fetch_cfs.MEMBERS):
        files = fetch_cfs.list_month_files(date, m)
        for li in range(LEADS):
            if li < len(files.get("pgbf", [])) and li < len(files.get("flxf", [])):
                tasks.append((mi, li, files["pgbf"][li], files["flxf"][li]))

    def run(t):
        mi, li, pg, fl = t
        r = fetch_member_lead(pg, fl)
        for k, v in r.items():
            raw[k][mi, li] = v

    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(run, tasks))
    lat = fetch_cfs.LAT
    psi850, _ = dyn_solver.streamfunction_potential(raw["u850"], raw["v850"], lat)
    psi200, chi200 = dyn_solver.streamfunction_potential(raw["u200"], raw["v200"], lat)
    arr = np.stack([psi850 * SCALE, psi200 * SCALE, chi200 * SCALE, raw["olr"]], axis=2).astype("float32")
    return arr


def dates_for(target, years, window):
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    return [d for d in fetch_cfs.analog_dates(target, years, window) if int(d[4:6]) == t.month]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    os.makedirs(OUT_DIR, exist_ok=True)
    dates = dates_for(a.target, range(int(y0), int(y1 or y0) + 1), a.window)
    t0 = time.time()
    failed = []
    for i, d in enumerate(dates):
        path = os.path.join(OUT_DIR, f"{d}.npz")
        if os.path.exists(path) and not a.force:
            continue
        try:
            arr = fetch_init(d)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"[{i + 1}/{len(dates)}] {d} 通信失敗: {e}", file=sys.stderr)
            if d not in fetch_cfs.KNOWN_BAD:
                failed.append(d)
            continue
        except Exception as e:
            print(f"[{i + 1}/{len(dates)}] {d} 読めない(飛ばす): {e}", file=sys.stderr)
            continue
        if np.isnan(arr).all():
            print(f"[{i + 1}/{len(dates)}] {d} データなし", file=sys.stderr)
            continue
        np.savez_compressed(path + ".tmp.npz", arr=arr, lat=fetch_cfs.LAT, lon=fetch_cfs.LON, vars=NAMES)
        os.replace(path + ".tmp.npz", path)
        print(f"[{i + 1}/{len(dates)}] {d} 保存 欠損率{np.isnan(arr).mean():.2%} 経過{time.time() - t0:.0f}s", flush=True)
    if failed:
        print(f"取得失敗 {len(failed)}件（再実行で取り直せる）: {failed[:5]}...", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
