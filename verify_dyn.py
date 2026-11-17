"""力学診断（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の予報を観測で照合し、確率の縮小係数 α を求める（verify_cps4.py・verify_cfs_vars.py と同じ方法）。

観測（NOAA PSL。観測そのものではないものを含む）:
  - 風: NCEP/NCAR 再解析の月平均 u・v（850・200hPa・2.5°）から、予報と同じ dyn_solver で ψ・χ を求める（同じ規約: ψ は東西平均を除く・χ は全球平均0）。
  - OLR: NOAA 補間 OLR（月平均・2.5°）。
方法: 年抜きの気候値（verify.evaluate）・ACC・三分位の BSS・最適な縮小係数 α。
  CPS4: ハインドキャスト 1993–2020（28年×10メンバー）を、指定した開始月について。
  CFS : 運用予報の初期日 2019–2025（対象と同じ月・前後15日）。月1（初月は部分月）は月平均の観測と合わないので照合しない。
**この照合は、対象の月（CFS は基準の初期日・CPS4 は開始月）の分だけ**。ほかの月は、その月の力学診断のデータを取得してから行う。
使い方: python verify_dyn.py --cps4 --month 11 [--write]
        python verify_dyn.py --cfs --target 20261112 [--write]
"""
import argparse
import datetime as dt
import os

import numpy as np
import xarray as xr

import baseline_offset
import calib
import charts
import cps4
import cps4_dyn
import dyn
import dyn_solver
import fetch_daily
import fetch_dyn
import verify
import verify_cps4

PSL = baseline_offset.PSL
NAMES = fetch_dyn.NAMES                      # psi850, psi200, chi200, olr
OBS_FILES = {
    "uwnd": (f"{PSL}/ncep.reanalysis.derived/pressure/uwnd.mon.mean.nc", "ncep_uwnd.mon.mean.nc"),
    "vwnd": (f"{PSL}/ncep.reanalysis.derived/pressure/vwnd.mon.mean.nc", "ncep_vwnd.mon.mean.nc"),
    "olr": (f"{PSL}/interp_OLR/olr.mon.mean.nc", "noaa_olr.mon.mean.nc"),                   # NOAA 補間 OLR（観測。2022年12月まで）
    "olr_ncep": (f"{PSL}/ncep.reanalysis.derived/other_gauss/ulwrf.ntat.mon.mean.nc", "ncep_ulwrf_ntat.mon.mean.nc"),   # NCEP/NCAR 再解析の大気上端の上向き長波（2026年まで・モデル由来）
}
YEARS_CFS = list(range(2019, 2026))


def obs_getter(olr_source="interp"):
    """観測 f(年, 月) → [4, 緯(73), 経(144)]（psi850, psi200, chi200, olr）。予報と同じ規約・単位。
    olr_source: "interp"=NOAA 補間 OLR（観測・2022年12月まで。CPS4 の1993–2020年の照合用）／"ncep"=NCEP/NCAR 再解析の大気上端の長波（2026年まで。CFS の2019–2025年の照合用・モデル由来で精度は下がる）。"""
    def load(key):
        url, name = OBS_FILES[key]
        return xr.open_dataset(baseline_offset.fetch(url, name), drop_variables=["time_bnds"])
    du, dv = load("uwnd"), load("vwnd")
    do = load("olr" if olr_source == "interp" else "olr_ncep")
    lat = du["lat"].values.astype("float64")
    t = du["time"].values.astype("datetime64[M]")
    u850, v850 = du["uwnd"].sel(level=850).values, dv["vwnd"].sel(level=850).values
    u200, v200 = du["uwnd"].sel(level=200).values, dv["vwnd"].sel(level=200).values
    psi850, _ = dyn_solver.streamfunction_potential(u850, v850, lat)
    psi200, chi200 = dyn_solver.streamfunction_potential(u200, v200, lat)
    arr = np.stack([psi850 * 1e-6, psi200 * 1e-6, chi200 * 1e-6], axis=1)                # [時間, 3, 緯, 経]
    vname = "olr" if olr_source == "interp" else "ulwrf"
    to = do["time"].values.astype("datetime64[M]")
    src = do[vname].values.astype("float32")
    if src.shape[1:] != (len(lat), du["lon"].shape[0]):                                   # ガウス格子 → 2.5°
        rg = fetch_daily.make_regrid(do["lat"].values, do["lon"].values)
        src = rg(src)
    olr = np.full((len(t),) + src.shape[1:], np.nan, dtype="float32")
    ix = {m: i for i, m in enumerate(to)}
    for i, m in enumerate(t):
        if m in ix:
            olr[i] = src[ix[m]]
    arr = np.concatenate([arr, olr[:, None]], axis=1).astype("float32")                  # [時間, 4, 緯, 経]
    arr = dyn._fix_convention(arr.transpose(0, 1, 2, 3), lat)                            # ψ: 東西平均を除く・χ: 全球平均0
    index = {(int(m.astype("datetime64[Y]").astype(int)) + 1970, int(m.astype(int) % 12) + 1): i for i, m in enumerate(t)}
    return lambda y, m: arr[index[(y, m)]]


def cps4_rows(month, ws, get):
    pl = "_p850-200"
    mm = f"{month:02d}"

    def gp(var, years, p=""):
        return os.path.join(cps4.C3S, f"jma_s4_{var}_monthly_mean_{years}{p}-{mm}_L1-6.grib")
    Hd, lat, lon = cps4_dyn.derive(gp("u_component_of_wind", "1993-2020", pl), gp("v_component_of_wind", "1993-2020", pl), month)
    Ho, _, _ = cps4_dyn.load_single(gp("top_thermal_radiation", "1993-2020"), month)
    sgn = -1.0 if np.nanmean(Ho) < 0 else 1.0
    Hd["olr"] = sgn * Ho
    H = {v: Hd[v][..., ::2, ::2] for v in NAMES}                                         # 1.25° → 2.5°
    years = verify_cps4.YEARS
    yr, off = np.array(years), np.zeros(len(years))
    rows = {v: [] for v in NAMES}
    for name, leads in verify_cps4.WINDOWS.items():
        O = []
        for y in years:
            v = []
            for k in leads:
                mi = month - 1 + k - 1
                v.append(get(y + mi // 12, mi % 12 + 1))
            O.append(np.mean(v, 0))
        O = np.stack(O)                                                                   # [年, 4, 緯, 経]
        for vi, var in enumerate(NAMES):
            F = H[var][:, :, [k - 1 for k in leads]].mean(axis=2)
            rows[var].append((name, verify.evaluate(F, O[:, vi], yr, off, years, ws)))
        print(f"  CPS4 {name} 完了", flush=True)
    return rows


def cfs_cases(target, window=15):
    """初期日ごとの事例 [(年, ずれ, 日付, arr[メンバー, リード, 4, 緯, 経])]（対象と同じ月の初期日だけ）。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    out = []
    for y in YEARS_CFS:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            if day.month != t.month:
                continue
            p = os.path.join(fetch_dyn.OUT_DIR, day.strftime("%Y%m%d") + ".npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)
            arr = z["arr"]
            arr = arr[[m for m in range(arr.shape[0]) if not np.isnan(arr[m]).all()]]
            out.append((y, d, day, dyn._fix_convention(arr, z["lat"])))
    return out


def cfs_rows(target, ws, get):
    mc = cfs_cases(target)
    myr = np.array([m[0] for m in mc])
    moff = np.array([float(m[1]) for m in mc])
    n_mem = min(m[3].shape[0] for m in mc)
    rows = {v: [] for v in NAMES}
    for name, leads in charts.PERIODS.items():
        if 0 in leads:
            print(f"  CFS {name}: 部分月のため月平均の観測と合わず照合しない", flush=True)
            continue
        Fall = np.stack([m[3][:n_mem][:, leads].mean(1) for m in mc])                    # [事例, メンバー, 4, 緯, 経]
        O = []
        for (y, d, day, _) in mc:
            vals = []
            for k in leads:
                mi = day.month - 1 + k
                vals.append(get(day.year + mi // 12, mi % 12 + 1))
            O.append(np.mean(vals, 0))
        O = np.stack(O)
        for vi, var in enumerate(NAMES):
            rows[var].append((name, verify.evaluate(Fall[:, :, vi], O[:, vi], myr, moff, YEARS_CFS, ws)))
        print(f"  CFS {name} 完了", flush=True)
    return rows


def pack(rows):
    return {var: {name: {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                         "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)} for name, r in rs}
            for var, rs in rows.items()}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cps4", action="store_true")
    g.add_argument("--cfs", action="store_true")
    ap.add_argument("--month", type=int, default=11, help="CPS4 の開始月")
    ap.add_argument("--target", default="20261112", help="CFS の基準の初期日（校正の枠）")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ws = {k: verify.weights(b) for k, b in verify.BOXES.items()}
    get = obs_getter("interp" if a.cps4 else "ncep")
    if a.cps4:
        rows = cps4_rows(a.month, ws, get)
    else:
        rows = cfs_rows(a.target, ws, get)
    for var, rs in rows.items():
        verify_cps4.print_rows(var, rs)
    if a.write:
        if a.cps4:
            calib.update_cps4(a.month, meta={"力学診断の方法": "verify_dyn.py: CPS4ハインドキャスト28年×10メンバーを、NCEP/NCAR再解析の風から算出した流線関数・速度ポテンシャルとNOAA補間OLRの月平均と照合・年抜き・BSS最良の縮小係数"},
                              alpha_var=pack(rows))
        else:
            calib.update_cfs(a.target, meta={"力学診断の方法": "verify_dyn.py: CFS(2019–2025の運用予報・初期日の前後・4メンバー)を、NCEP/NCAR再解析の風から算出した流線関数・速度ポテンシャルとNCEP/NCAR再解析のOLR（大気上端の長波・補間OLRは2022年で終了のため）の月平均と照合・年抜き・BSS最良の縮小係数（M1は照合しない）"},
                             alpha_var=pack(rows))
        print("追記: calibration.json")


if __name__ == "__main__":
    main()
