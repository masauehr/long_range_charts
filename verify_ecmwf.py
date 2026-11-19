"""C3S の ECMWF SEAS5 のハインドキャスト（1993–2016・24年×25メンバー）を、観測（NOAA）の月平均と照合する。

verify.py の evaluate を使う（気候値は照合する年を除いた年抜き・指標は ACC と三分位確率の BSS・縮小係数 α）。
verify_cps4.py と同じ方法・同じ観測（t2m=NCEP/NCAR再解析・prate=GPCP v2.3）。違い:
- 事例=24年（基準日11/1の1回/年）、メンバー=25（予報本番は51メンバー）。格子は1°→2.5°に補間して照合する。
- 強いEl Niño年は 1997・2015（期間内の両方）。
使い方: python verify_ecmwf.py [--vars t2m prate] [--month 11] [--write]
  --write は calibration.json の ecmwf[開始月] に alpha_var[変数][窓] を追記する。
"""
import argparse
import os

import numpy as np

import cps4
import fetch_daily
import verify
import verify_cps4

START_MONTH = 11
YEARS = list(range(1993, 2017))
WINDOWS = verify_cps4.WINDOWS
CNAME = verify_cps4.CNAME


def verify_var(var, ws):
    path = os.path.join(cps4.C3S, f"ecmwf_s51_{CNAME[var]}_monthly_mean_{YEARS[0]}-{YEARS[-1]}-{START_MONTH:02d}_L1-6.grib")
    arr, lat, lon = cps4.load(path, START_MONTH)                        # [年, メンバー, リード, 緯(1°), 経(1°)]
    assert arr.shape[0] == len(YEARS), arr.shape
    conv = cps4.VARS[CNAME[var]][1]
    rg = fetch_daily.make_regrid(lat, lon)                              # 1°→2.5°（verify の格子と同じ）
    H = rg(np.ascontiguousarray(conv(arr), dtype="float32"))
    assert H.shape[-2:] == (len(verify.LAT), len(verify.LON)), H.shape
    verify_cps4.YEARS = YEARS                                           # 観測の取得年（t2m）をこの期間にする
    get = verify_cps4.obs_getter(var)
    yr = np.array(YEARS)
    off = np.zeros(len(YEARS))
    rows = []
    for name, leads in WINDOWS.items():
        F = H[:, :, [k - 1 for k in leads]].mean(axis=2)                # [年, メンバー, 緯, 経]
        O = []
        for y in YEARS:
            v = []
            for k in leads:
                mi = START_MONTH - 1 + k - 1
                v.append(get(y + mi // 12, mi % 12 + 1))
            O.append(np.mean(v, 0))
        rows.append((name, verify.evaluate(F, np.stack(O), yr, off, YEARS, ws)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vars", nargs="*", default=["t2m", "prate"])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--month", type=int, default=11, help="開始月（ハインドキャストの基準日=その月1日）。既定は11")
    a = ap.parse_args()
    global START_MONTH
    START_MONTH = a.month
    ws = {k: verify.weights(b) for k, b in verify.BOXES.items()}
    results = {}
    for var in a.vars:
        results[var] = verify_var(var, ws)
        verify_cps4.print_rows(var, results[var])
    if a.write:
        import calib
        calib.update_ecmwf(
            START_MONTH,
            meta={"方法": "verify_ecmwf.py: ECMWF SEAS5（C3S・system 51）のハインドキャスト1993–2016(24年×25メンバー)を観測の月平均と照合・年抜き・BSS最良の縮小係数。"
                        "格子は1°→2.5°へ補間。観測: t2m=NCEP/NCAR再解析, prate=GPCP v2.3",
                  "注意": "事例は24年。ハインドキャストは25メンバーで、本番の51メンバーより少ない。"},
            alpha_var={var: {name: {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                                    "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)}
                             for name, r in rows} for var, rows in results.items()})
        print("追記: calibration.json（ecmwf）")


if __name__ == "__main__":
    main()
