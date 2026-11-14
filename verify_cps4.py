"""C3S の JMA CPS4 のハインドキャスト（1993–2020・28年×10メンバー）を、観測（NOAA）の月平均と照合する。

verify.py の evaluate を使う（気候値は照合する年を除いた年抜き・指標は ACC と三分位確率の BSS・縮小係数 α）。
- 事例=28年（基準日11/1の1回/年）。メンバー=10（予報本番の155メンバーより少ない）。
- 観測（NOAA PSL。観測そのものではない再解析・統合解析を含む）:
    t2m  : NCEP/NCAR 再解析の日別2m気温（baseline_offset.py で取得済み）から月平均
    prate: GPCP v2.3 月平均降水（衛星＋地上の統合解析・2.5°）
    z500 : NCEP/NCAR 再解析の月平均 500hPa 高度
    sst  : ERSSTv5 月平均海面水温（2°）
- 強いEl Niño年（1997・2015）とそれ以外で ACC を分けて見る。
使い方: python verify_cps4.py [--vars t2m prate z500 sst] [--write]
  --write は calibration.json の alpha_var[変数][窓] に追記する（t2m は従来の alpha にも入っている）。
"""
import argparse
import json
import os

import numpy as np
import xarray as xr

import baseline_offset
import clim
import cps4
import fetch_daily
import verify

START_MONTH = 11
YEARS = list(range(1993, 2021))
STRONG_EL_NINO = [1997, 2015]
WINDOWS = {"L1": [1], "L2": [2], "L3": [3], "L4": [4], "L5": [5], "L6": [6], "L2-4": [2, 3, 4], "L1-3": [1, 2, 3]}
PSL = baseline_offset.PSL
OBS_FILES = {   # 変数 -> (URL, 保存名, 変数名, 選択)
    "prate": (f"{PSL}/gpcp/precip.mon.mean.nc", "gpcp_precip.mon.mean.nc", "precip", None),
    "z500": (f"{PSL}/ncep.reanalysis.derived/pressure/hgt.mon.mean.nc", "ncep_hgt.mon.mean.nc", "hgt", 500),
    "sst": (f"{PSL}/noaa.ersst.v5/sst.mnmean.nc", "ersst_v5_sst.mnmean.nc", "sst", None),
}
CNAME = {"t2m": "2m_temperature", "prate": "total_precipitation", "z500": "geopotential", "sst": "sea_surface_temperature"}


def obs_getter(var):
    """月平均の観測 f(年, 月) → [緯(73), 経(144)]（2.5°・北→南・0〜357.5E）。"""
    if var == "t2m":
        obs = verify.load_obs(YEARS + [YEARS[-1] + 1])
        return lambda y, m: verify.obs_month(obs, y, m)
    url, name, vname, level = OBS_FILES[var]
    ds = xr.open_dataset(baseline_offset.fetch(url, name), drop_variables=["time_bnds"])      # GPCP の time_bnds は単位の書式が不正
    da = ds[vname]
    if level is not None:
        da = da.sel(level=level)
    rg = fetch_daily.make_regrid(ds["lat"].values, ds["lon"].values)

    def f(y, m):
        a = da.sel(time=f"{y}-{m:02d}").values
        return rg(np.asarray(a[0] if a.ndim == 3 else a, dtype="float32"))
    return f


def verify_var(var, ws):
    path = os.path.join(cps4.C3S, f"jma_s4_{CNAME[var]}_monthly_mean_1993-2020-{START_MONTH:02d}_L1-6.grib")
    arr, lat, lon = cps4.load(path, START_MONTH)                       # [年, メンバー, リード, 緯, 経]
    conv = cps4.VARS[CNAME[var]][1]
    H = conv(arr)[..., ::2, ::2]                                       # 1.25°→2.5°（verify の格子と同じ）
    assert H.shape[-2:] == (len(verify.LAT), len(verify.LON)), H.shape
    get = obs_getter(var)
    yr = np.array(YEARS)
    off = np.zeros(len(YEARS))
    rows = []
    for name, leads in WINDOWS.items():
        F = H[:, :, [k - 1 for k in leads]].mean(axis=2)               # [年, メンバー, 緯, 経]
        O = []
        for y in YEARS:
            v = []
            for k in leads:
                mi = START_MONTH - 1 + k - 1
                v.append(get(y + mi // 12, mi % 12 + 1))
            O.append(np.mean(v, 0))
        rows.append((name, verify.evaluate(F, np.stack(O), yr, off, YEARS, ws)))
    return rows


def print_rows(var, rows):
    print(f"\n### {var}\n| 窓 | 領域 | ACC(年平均) | ACCの年ごとの範囲 | ACC 強いEl Niño年(1997・2015) | ACC それ以外 | BSS上位1/3 | BSS下位1/3 | 最適α | α適用後BSS |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in rows:
        for k, v in r.items():
            ens = [x for y, x in v["acc_year"].items() if y in STRONG_EL_NINO]      # 該当年が無い期間（CFSの2019–2025）は「—」
            en = f"{np.mean(ens):+.2f}" if ens else "—"
            ot = np.mean([x for y, x in v["acc_year"].items() if y not in STRONG_EL_NINO])
            print(f"| {name} | {k} | {v['acc']:+.2f} | {v['acc_min']:+.2f}〜{v['acc_max']:+.2f} | {en} | {ot:+.2f} | "
                  f"{v['bss_u']:+.2f} | {v['bss_l']:+.2f} | {v['alpha']:.2f} | {v['bss_alpha']:+.2f} |", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vars", nargs="*", default=["t2m", "prate", "z500", "sst"])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ws = {k: verify.weights(b) for k, b in verify.BOXES.items()}
    results = {}
    for var in a.vars:
        results[var] = verify_var(var, ws)
        print_rows(var, results[var])
    if a.write:
        p = os.path.join(clim.ROOT, "calibration.json")
        cal = json.load(open(p, encoding="utf-8"))
        cal.setdefault("alpha_var", {})
        cal["メタ_CPS4"] = {"方法": "verify_cps4.py: CPS4ハインドキャスト1993–2020(28年×10メンバー)を観測の月平均と照合・年抜き・BSS最良の縮小係数。"
                                 "観測: t2m=NCEP/NCAR再解析, prate=GPCP v2.3, z500=NCEP/NCAR再解析, sst=ERSSTv5",
                          "注意": "事例は28年。ハインドキャストは10メンバーで、本番の155メンバー(ラグ)より少ない。"}
        for var, rows in results.items():
            cal["alpha_var"][var] = {name: {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                                            "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)}
                                     for name, r in rows}
            if var == "t2m":                       # 従来の alpha（全変数の既定）も更新
                for name, r in rows:
                    cal["alpha"][name] = cal["alpha_var"]["t2m"][name]
        if "t2m" not in results:                   # t2m は従来の alpha（照合済み）を alpha_var にも写す
            for name in WINDOWS:
                if name in cal["alpha"]:
                    cal["alpha_var"].setdefault("t2m", {})[name] = cal["alpha"][name]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
        print("追記: calibration.json")


if __name__ == "__main__":
    main()
