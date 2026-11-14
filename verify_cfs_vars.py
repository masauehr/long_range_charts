"""CFS（2019–2025 の運用予報）の降水・Z500・水温を、観測で照合して、窓ごとの縮小係数 α を求める（2m気温は verify.py）。

窓: 週平均 W1〜W4・J28（日別データ）、月平均 M1〜M4・Q1（暦月）。気候値は照合する年を除いた年抜き（verify.evaluate）。
観測（NOAA PSL。観測そのものではないものを含む）:
  prate 週平均: NCEP/NCAR 再解析の日別降水（モデル由来で精度は低め）／月平均: GPCP v2.3（M1 は部分月で合わないため照合しない）
  z500  週平均・月平均: NCEP/NCAR 再解析の日別 500hPa 高度（月平均は日別から作る。M1 の部分月も合う）
  pot5  月平均: ERSSTv5 海面水温（CFS の海洋5m水温と比べる。M1 は照合しない）
注意: 独立な年は7つだけ・α は同じ事例で当てており過学習ぎみ。
使い方: python verify_cfs_vars.py --target 20261112 [--vars prate z500 pot5] [--write]
  --write は calibration.json の alpha_var[変数][窓] に追記する。
"""
import argparse
import os

import numpy as np

import charts
import clim
import verify
import verify_cps4
import weekly

YEARS = list(range(2019, 2026))
WEEK_WINDOWS = {**weekly.WEEKS, "J28": weekly.JMA_WINDOWS["J28"]}
MONTH_GETTER = {"prate": "prate", "pot5": "sst"}        # 月平均の観測（GPCP・ERSST）


def run_var(var, target, ws, window=7, monthly_window=15):
    rows = []
    # --- 週平均（日別データ）
    if var in verify.DAILY_VI:
        xs, meta = verify.cases(target, YEARS, window, verify.DAILY_VI[var])
        obs = verify.load_obs_var(var, YEARS + [YEARS[-1] + 1])
        yr = np.array([m[0] for m in meta])
        off = np.array([float(m[1]) for m in meta])
        for name, span in WEEK_WINDOWS.items():
            F = np.stack([z[:, span[0] - 1:span[1]].mean(1) for z in xs])
            O = np.stack([verify.obs_window(obs, m[2], span) for m in meta])
            rows.append((name, verify.evaluate(F, O, yr, off, YEARS, ws)))
            print(f"  {var} {name} 完了", flush=True)
    # --- 月平均（暦月）
    mc = verify.monthly_cases(target, YEARS, monthly_window, verify.MONTHLY_VI[var])
    myr = np.array([m[0] for m in mc])
    moff = np.array([float(m[1]) for m in mc])
    if var in MONTH_GETTER:
        get = verify_cps4.obs_getter(MONTH_GETTER[var])
    else:
        dobs = verify.load_obs_var(var, YEARS + [YEARS[-1] + 1])
    for name, leads in charts.PERIODS.items():
        if var in MONTH_GETTER and 0 in leads:
            print(f"  {var} {name}: 部分月のため月平均の観測と合わず照合しない", flush=True)
            continue
        F = np.stack([m[3][:, leads].mean(1) for m in mc])
        O = []
        for (y, d, day, _) in mc:
            vals = []
            for k in leads:
                mi = day.month - 1 + k
                yy, mm = day.year + mi // 12, mi % 12 + 1
                vals.append(get(yy, mm) if var in MONTH_GETTER else verify.obs_month(dobs, yy, mm, day.day if k == 0 else 1))
            O.append(np.mean(vals, 0))
        rows.append((name, verify.evaluate(F, np.stack(O), myr, moff, YEARS, ws)))
        print(f"  {var} {name} 完了", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--vars", nargs="*", default=["prate", "z500", "pot5"])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ws = {k: verify.weights(b) for k, b in verify.BOXES.items()}
    results = {}
    for var in a.vars:
        results[var] = run_var(var, a.target, ws)
        verify_cps4.print_rows(var, results[var])
    if a.write:
        import calib
        calib.update_cfs(
            a.target,
            meta={"変数別の方法": "verify_cfs_vars.py: CFS(2019–2025の運用予報・初期日の前後・4メンバー)の降水・Z500・水温を観測で照合・年抜き・BSS最良の縮小係数",
                  "変数別の観測": "prate=週平均は再解析の日別降水(精度低め)・月平均はGPCP v2.3(M1除く), z500=再解析の日別高度, pot5=ERSSTv5(M1除く)"},
            alpha_var={var: {name: {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                                    "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)}
                             for name, r in rows} for var, rows in results.items()})
        print("追記: calibration.json")


if __name__ == "__main__":
    main()
