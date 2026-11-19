"""ECMWF SEAS5（C3S・system 51）の力学診断（流線関数 850・200hPa・速度ポテンシャル 200hPa・OLR）の偏差・確率の図を作る。

入力: data/c3s/ecmwf_s51_{u,v}_component_of_wind_monthly_mean_{2026|1993-2016}_p850-200-{月}_L1-6.grib・ecmwf_s51_top_thermal_radiation_*（fetch_c3s.py --ecmwf-dyn）。
  予報（51メンバー）とハインドキャスト（1993–2016の24年×25メンバー）の風から、メンバー・リードごとに dyn_solver で ψ・χ を求め、
  cps4.stats_for と同じ方法で偏差・確率にする（cps4_dyn.py の ECMWF 版）。
格子: ECMWF は1°（緯度±89.5度で極を含まない）。dyn_solver は先頭・末尾の行を極とみなすので、極を含む181行の格子へ補間して解き、結果を元の180行へ戻す。
出力: output/ecmwf_{基準日}_{変数}_{期間}_{領域}.png（変数 psi850・psi200・chi200・olr）、data/ecmwf_{基準日}_{変数}.npz、output/dist_ecmwf_{基準日}.json への追記。
確率の縮小は、観測との照合（verify_dyn.py --ecmwf）で求めた係数を適用する（照合が無い月・期間は未補正と表示）。
公開: ローカルのみ。

使い方: python ecmwf_dyn.py --year 2026 --month 11
"""
import argparse
import os

import numpy as np

import charts
import clim
import cps4
import cps4_dyn
import distview
import dyn
import dyn_solver
import ecmwf_seas5

SCALE = cps4_dyn.SCALE
POLE_LAT = np.arange(90.0, -90.1, -1.0)                    # 極を含む1°格子（181行）


def to_pole_grid(a, lat):
    """緯度（北→南・中心値 89.5…-89.5）の配列[..., 緯, 経]を、極を含む181行（90…-90）へ線形補間する（両端は端の行の値）。"""
    p = np.clip((lat[0] - POLE_LAT) / (lat[0] - lat[1]), 0, len(lat) - 1)      # 元の行番号（小数）
    i0 = np.floor(p).astype(int)
    i1 = np.minimum(i0 + 1, len(lat) - 1)
    w = (p - i0).astype("float32")[:, None]
    return a[..., i0, :] * (1 - w) + a[..., i1, :] * w


def from_pole_grid(a, lat):
    """181行（90…-90）の配列[..., 緯, 経]を、元の緯度 lat（北→南）へ線形補間して戻す。"""
    p = np.clip((90.0 - lat), 0, len(POLE_LAT) - 1)                             # 181行の行番号（1°刻み）
    i0 = np.floor(p).astype(int)
    i1 = np.minimum(i0 + 1, len(POLE_LAT) - 1)
    w = (p - i0).astype("float32")[:, None]
    return a[..., i0, :] * (1 - w) + a[..., i1, :] * w


def derive(path_u, path_v, start_month):
    """風の GRIB から {変数: 配列[年, メンバー, リード, 緯, 経]}（psi850・psi200・chi200）を作る。"""
    U, lat, lon = cps4_dyn.load_levels(path_u, start_month, (850, 200))
    V, _, _ = cps4_dyn.load_levels(path_v, start_month, (850, 200))
    res = {}
    for name, lv, which in (("psi850", 850, 0), ("psi200", 200, 0), ("chi200", 200, 1)):
        u, v = U[lv], V[lv]
        out = np.full(u.shape, np.nan, dtype="float32")
        for ld in range(u.shape[2]):                      # リードごとに解く（メモリを抑える）
            uu, vv = to_pole_grid(u[:, :, ld], lat), to_pole_grid(v[:, :, ld], lat)
            psi, chi = dyn_solver.streamfunction_potential(uu, vv, POLE_LAT)
            f = dyn_solver.remove_global_mean((psi if which == 0 else chi) * SCALE, POLE_LAT)   # 全球平均0（cps4_dyn と同じ規約）
            out[:, :, ld] = from_pole_grid(f, lat)
        res[name] = out
    return res, lat, lon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=11)
    ap.add_argument("--hind", default="1993-2016")
    ap.add_argument("--periods", nargs="*", default=["L1", "L2", "L3", "L4", "L2-4"])
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    a = ap.parse_args()
    periods = cps4.make_periods(a.month)
    init = f"{a.year}{a.month:02d}01"
    mm = f"{a.month:02d}"

    def gp(var, years, pl):
        return os.path.join(cps4.C3S, f"ecmwf_s51_{var}_monthly_mean_{years}{pl}-{mm}_L1-6.grib")
    pl = "_p850-200"
    Fd, lat, lon = derive(gp("u_component_of_wind", a.year, pl), gp("v_component_of_wind", a.year, pl), a.month)
    Hd, _, _ = derive(gp("u_component_of_wind", a.hind, pl), gp("v_component_of_wind", a.hind, pl), a.month)
    Fo, _, _ = cps4_dyn.load_single(gp("top_thermal_radiation", a.year, ""), a.month)
    Ho, _, _ = cps4_dyn.load_single(gp("top_thermal_radiation", a.hind, ""), a.month)
    sgn = -1.0 if np.nanmean(Ho) < 0 else 1.0                 # 大気上端の熱放射は上向きが負の慣習 → OLR（外向き正）にそろえる
    Fd["olr"], Hd["olr"] = sgn * Fo, sgn * Ho
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
                path = os.path.join(charts.OUT, f"ecmwf_{init}_{short}_{pname}_{rg}.png")
                charts.render(short, rg, s["anom"], s["p_upper"], s["p_lower"], F.shape[0], lat, lon, init=init, label=label,
                              out_path=path, clim_text=f"ECMWF SEAS5 のハインドキャスト {a.hind}年（{H.shape[0]}年×{H.shape[1]}メンバー）",
                              member_text=f"ECMWF SEAS5（C3S経由）{F.shape[0]}メンバー（基準日{a.month}/1）。",
                              alpha=charts.load_alpha_strict(pname, rg, short, init, "ecmwf"),
                              calib_basis=f"ECMWF SEAS5ハインドキャスト{H.shape[0]}年（{H.shape[1]}メンバー）と観測（{cps4.OBS_NAME[short]}）との照合", alpha_scope="",
                              title_text=f"ECMWF SEAS5 {a.year}年{a.month}月1日基準",
                              extra_notes=ecmwf_seas5.COPERNICUS_NOTE.format(year=a.year) + "\n" + dyn.NOTE[short],
                              source_text="ECMWF SEAS5（Copernicus C3S 経由）を加工して作成。ECMWF・C3Sの推奨を示すものではない。")
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
        np.savez_compressed(os.path.join(clim.DATA, f"ecmwf_{init}_{short}.npz"), lat=lat, lon=lon, **out)
    dist.write("ecmwf", init)


if __name__ == "__main__":
    main()
