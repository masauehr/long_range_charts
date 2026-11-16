"""JMA/MRI-CPS4（C3S 経由）の力学診断（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の偏差・確率の図を作る。

入力: data/c3s/jma_s4_{u,v}_component_of_wind_monthly_mean_{2026|1993-2020}_p850-200-{月}_L1-6.grib・jma_s4_top_thermal_radiation_*（fetch_c3s.py --dyn）。
  予報（155メンバー）とハインドキャスト（1993–2020の28年×10メンバー）の風から、メンバー・リードごとに dyn_solver で ψ・χ を求め、
  cps4.stats_for と同じ方法（ハインドキャストの気候値・三分位点・メンバーの割合）で偏差・確率にする。
出力: output/cps4_{基準日}_{変数}_{期間}_{領域}.png（変数 psi850・psi200・chi200・olr）、data/cps4_{基準日}_{変数}.npz、output/dist_cps4_{基準日}.json への追記。
確率の縮小（観測との照合）はまだ無いので**未補正**。

使い方: python cps4_dyn.py --year 2026 --month 11
"""
import argparse
import os

import numpy as np

import charts
import clim
import cps4
import distview
import dyn
import dyn_solver

SCALE = 1e-6
OLR_NOTE = None


def load_levels(path, start_month, levels):
    """GRIB（複数の気圧面）を読む。戻り値: ({気圧面: 配列[年, メンバー, リード, 緯, 経]}, lat, lon)。年は dataDate の年。"""
    import pygrib
    cells = {lv: {} for lv in levels}
    lat = lon = None
    for m in pygrib.open(path):
        lv = m["level"]
        if lv not in cells:
            continue
        y, mem, ld = m["dataDate"] // 10000, m["perturbationNumber"], cps4.lead_of(m, start_month)
        cells[lv][(y, mem, ld)] = cps4.to_float(m.values)
        if lat is None:
            la, lo = m.latlons()
            lat, lon = la[:, 0], lo[0, :]
    out = {}
    for lv, c in cells.items():
        years = sorted({k[0] for k in c})
        mems = sorted({k[1] for k in c})
        shape = next(iter(c.values())).shape
        arr = np.full((len(years), len(mems), cps4.LEADS) + shape, np.nan, dtype="float32")
        for (y, mem, ld), v in c.items():
            if ld <= cps4.LEADS:
                arr[years.index(y), mems.index(mem), ld - 1] = v
        out[lv] = arr
    return out, lat, lon


def load_single(path, start_month):
    """単一面の GRIB（OLR など）。戻り値: (配列[年, メンバー, リード, 緯, 経], lat, lon)。"""
    arr, lat, lon = cps4.load(path, start_month)
    return arr, lat, lon


def derive(path_u, path_v, start_month):
    """風の GRIB から {変数: 配列[年, メンバー, リード, 緯, 経]}（psi850・psi200・chi200）を作る。"""
    U, lat, lon = load_levels(path_u, start_month, (850, 200))
    V, _, _ = load_levels(path_v, start_month, (850, 200))
    res = {}
    for name, lv, which in (("psi850", 850, 0), ("psi200", 200, 0), ("chi200", 200, 1)):
        u, v = U[lv], V[lv]
        out = np.full(u.shape, np.nan, dtype="float32")
        for ld in range(u.shape[2]):                      # リードごとに解く（メモリを抑える）
            uu, vv = u[:, :, ld], v[:, :, ld]
            psi, chi = dyn_solver.streamfunction_potential(uu, vv, lat)
            out[:, :, ld] = (psi if which == 0 else chi) * SCALE
        res[name] = out
    return res, lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=11)
    ap.add_argument("--hind", default="1993-2020")
    ap.add_argument("--periods", nargs="*", default=["L1", "L2", "L3", "L4", "L2-4"])
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    a = ap.parse_args()
    periods = cps4.make_periods(a.month)
    init = f"{a.year}{a.month:02d}01"
    mm = f"{a.month:02d}"

    def gp(var, years, pl):
        return os.path.join(cps4.C3S, f"jma_s4_{var}_monthly_mean_{years}{pl}-{mm}_L1-6.grib")
    pl = "_p850-200"
    Fd, lat, lon = derive(gp("u_component_of_wind", a.year, pl), gp("v_component_of_wind", a.year, pl), a.month)
    Hd, _, _ = derive(gp("u_component_of_wind", a.hind, pl), gp("v_component_of_wind", a.hind, pl), a.month)
    # OLR（大気上端の熱放射。符号・単位は取得したデータで確認して W/m² の「外向き正」にそろえる）
    Fo, _, _ = load_single(gp("top_thermal_radiation", a.year, ""), a.month)
    Ho, _, _ = load_single(gp("top_thermal_radiation", a.hind, ""), a.month)
    sgn = -1.0 if np.nanmean(Ho) < 0 else 1.0                 # ECMWF 系は上向きが負の慣習
    scale = 1.0 if abs(np.nanmean(Ho)) < 1e4 else 1.0 / (30 * 86400.0)   # 積算値（J/m²）なら秒で割る概算（要確認）
    Fd["olr"], Hd["olr"] = sgn * scale * Fo, sgn * scale * Ho
    print(f"OLR: ハインドキャスト平均 {float(np.nanmean(Hd['olr'])):.1f}（W/m² のはず）・符号係数 {sgn}", flush=True)
    dist = distview.Collector()
    for short in ("psi850", "psi200", "chi200", "olr"):
        F, H = Fd[short][0], Hd[short]                        # F[メンバー,リード,緯,経]  H[年,メンバー,リード,緯,経]
        print(f"{short}: 予報{F.shape} ハインドキャスト{H.shape}", flush=True)
        out = {}
        for pname in a.periods:
            leads, label = periods[pname]
            s = cps4.stats_for(F, H, leads)
            out.update({f"{pname}_{k}": v for k, v in s.items()})
            dist.add(short, pname, cps4.period_fields(H, leads).reshape(-1, *F.shape[2:]), cps4.period_fields(F, leads), lat, lon)
            for rg in a.regions:
                path = os.path.join(charts.OUT, f"cps4_{init}_{short}_{pname}_{rg}.png")
                charts.render(short, rg, s["anom"], s["p_upper"], s["p_lower"], F.shape[0], lat, lon, init=init, label=label,
                              out_path=path, clim_text="JMA/MRI-CPS4 のハインドキャスト 1993–2020年（28年×10メンバー）",
                              member_text=f"JMA/MRI-CPS4（C3S経由）{F.shape[0]}メンバー（基準日{a.month}/1の前後31初期値のラグ）。",
                              alpha=None, title_text=f"JMA CPS4 {a.year}年{a.month}月1日基準",
                              extra_notes=cps4.COPERNICUS_NOTE.format(year=a.year) + "\n" + dyn.NOTE[short],
                              source_text="JMA/MRI-CPS4（Copernicus C3S 経由）を加工して作成。気象庁・C3Sの推奨を示すものではない。")
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
        np.savez_compressed(os.path.join(clim.DATA, f"cps4_{init}_{short}.npz"), lat=lat, lon=lon, **out)
    dist.write("cps4", init)


if __name__ == "__main__":
    main()
