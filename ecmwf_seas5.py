"""C3S の ECMWF SEAS5（system 51。fetch_c3s.py --ecmwf の GRIB）から、ハインドキャスト基準の偏差・三分位確率を作り、作図する。

基準: ハインドキャスト 1993–2016（24年×25メンバー=600/リード）。
  偏差   = 予報メンバー平均 − ハインドキャスト全メンバー平均
  確率   = 予報51メンバーのうち、ハインドキャストの三分位点（33.3/66.7%）を超える/下回る割合
期間: リード1〜6（初期月の月平均〜6か月先）と、3か月平均。cps4.py と同じ定義。
注意: 予報は51メンバー、ハインドキャストは25メンバー（メンバー数が違う）。格子は1°×1°。
      確率の縮小係数は verify_ecmwf.py --write（観測との照合）で求めた calibration.json の ecmwf[開始月]。無い窓は「未補正」と図に出る。
出典: ECMWF SEAS5。C3S（Copernicus Climate Change Service）経由。加工して作成。
公開: ローカルのみ（build_site.py の PUBLIC_SERIES に入れない）。追加ライセンスの本文確認後に判断する。

使い方:
    python fetch_c3s.py --ecmwf --year 2026 --month 11      # 先に取得
    python ecmwf_seas5.py --year 2026 --month 11
"""
import argparse
import os

import numpy as np

import charts
import clim
import cps4
import distview

C3S = cps4.C3S
COPERNICUS_NOTE = (
    "Contains modified Copernicus Climate Change Service information {year}. Neither the European Commission nor ECMWF is "
    "responsible for any use that may be made of the Copernicus information or data it contains.\n"
    "ECMWF SEAS5（C3S の system 51）。予報51メンバー・ハインドキャスト25メンバー×24年（メンバー数が違う）。")
# 取得済みの変数（fetch_c3s.ECMWF_VARS に合わせる）。C3S名 -> (短縮名, 単位変換)。cps4.VARS と同じ換算
VARS = {k: v for k, v in cps4.VARS.items() if k in ("2m_temperature", "total_precipitation", "geopotential", "sea_surface_temperature")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=11)
    ap.add_argument("--hind", default="1993-2016")
    ap.add_argument("--vars", nargs="*", default=["t2m", "prate", "z500", "sst"])
    ap.add_argument("--periods", nargs="*", default=["L1", "L2", "L3", "L4", "L2-4"])
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    a = ap.parse_args()
    os.makedirs(clim.DATA, exist_ok=True)
    periods = cps4.make_periods(a.month)
    name_of = {v[0]: k for k, v in VARS.items()}
    init = f"{a.year}{a.month:02d}01"
    dist = distview.Collector()
    for short in a.vars:
        cname = name_of[short]
        conv = VARS[cname][1]
        pf = os.path.join(C3S, f"ecmwf_s51_{cname}_monthly_mean_{a.year}-{a.month:02d}_L1-6.grib")
        ph = os.path.join(C3S, f"ecmwf_s51_{cname}_monthly_mean_{a.hind}-{a.month:02d}_L1-6.grib")
        F, lat, lon = cps4.load(pf, a.month)
        H, _, _ = cps4.load(ph, a.month)
        F, H = conv(F[0]), conv(H)                                    # F[メンバー,リード,緯,経]、H[年,メンバー,リード,緯,経]
        # 緯度が北→南で降順（89.5→-89.5）。charts.render は cps4 と同じ並びを前提にしているので、そのまま渡す
        print(f"{short}: 予報{F.shape} ハインドキャスト{H.shape}", flush=True)
        out = {}
        for pname in a.periods:
            leads, label = periods[pname]
            s = cps4.stats_for(F, H, leads)
            dist.add(short, pname, cps4.period_fields(H, leads).reshape(-1, *F.shape[2:]), cps4.period_fields(F, leads), lat, lon)
            out.update({f"{pname}_{k}": v for k, v in s.items()})
            for rg in a.regions:
                path = os.path.join(charts.OUT, f"ecmwf_{init}_{short}_{pname}_{rg}.png")
                charts.render(short, rg, s["anom"], s["p_upper"], s["p_lower"], F.shape[0], lat, lon, init=init,
                              label=label, out_path=path,
                              clim_text=f"ECMWF SEAS5 のハインドキャスト {a.hind}年（{len(H)}年×{H.shape[1]}メンバー）",
                              member_text=f"ECMWF SEAS5（C3S経由）{F.shape[0]}メンバー（基準日{a.month}/1）。",
                              alpha=charts.load_alpha(pname, rg, short, init, "ecmwf"),
                              calib_basis=f"ECMWF SEAS5ハインドキャスト{len(H)}年（{H.shape[1]}メンバー）と観測（{cps4.OBS_NAME[short]}）との照合",
                              alpha_scope=("" if charts.has_var_alpha(pname, short, init, "ecmwf") else "。2m気温の係数を仮に適用"),
                              title_text=f"ECMWF SEAS5 {a.year}年{a.month}月1日基準",
                              extra_notes=COPERNICUS_NOTE.format(year=a.year),
                              source_text="ECMWF SEAS5（Copernicus C3S 経由）を加工して作成。ECMWF・C3Sの推奨を示すものではない。")
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
        np.savez_compressed(os.path.join(clim.DATA, f"ecmwf_{init}_{short}.npz"), lat=lat, lon=lon, **out)
    dist.write("ecmwf", init)


if __name__ == "__main__":
    main()
