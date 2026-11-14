"""C3S の JMA CPS4（fetch_c3s.py の GRIB）から、ハインドキャスト基準の偏差・三分位確率を作り、作図する。

基準: ハインドキャスト 1993–2020（28年×10メンバー=280/リード）。気象庁の季節予報と同じ系統の基準。
  偏差   = 予報メンバー平均 − ハインドキャスト全メンバー平均
  確率   = 予報155メンバーのうち、ハインドキャストの三分位点（33.3/66.7%）を超える/下回る割合
期間: リード1〜6（初期月の月平均〜6か月先）と、3か月平均（リード2〜4=12〜2月 など）。
注意: 予報の基準日は11/1で、前後31初期値のラグアンサンブル（155メンバー）。ハインドキャストは10メンバー。
出典: JMA/MRI-CPS4。C3S（Copernicus Climate Change Service）経由。加工して作成。

使い方:
    python cps4.py --year 2026 --month 11
"""
import argparse
import datetime as dt
import os

import numpy as np
import pygrib

import charts
import clim

C3S = os.path.join(clim.DATA, "c3s")
# 図の下端に付ける出典・免責（NOTICE.md 参照）。Copernicus の標準的な表示文言＋JMA提供分の免責
COPERNICUS_NOTE = (
    "Generated using Copernicus Climate Change Service information {year}. Neither the European Commission nor ECMWF is "
    "responsible for any use that may be made of the Copernicus information or data it contains.\n"
    "JMA/MRI-CPS4 は気象庁が C3S に提供したデータで、提供元は品質・継続性を保証せず責任を負わない（C3S追加ライセンス）。"
    "データセット DOI: 10.24381/cds.68dd14c3。")
# 変数: C3S名 -> (短縮名, 単位変換)
VARS = {
    "2m_temperature": ("t2m", lambda a: a - 273.15),
    "total_precipitation": ("prate", lambda a: a * 86400.0 * 1000.0),   # m/s → mm/日（C3Sの降水は m s-1 の平均の可能性。要確認）
    "geopotential": ("z500", lambda a: a / 9.80665),                    # m2/s2 → gpm
    "sea_surface_temperature": ("sst", lambda a: a - 273.15),
}
LEADS = 6
OBS_NAME = {"t2m": "再解析の2m気温", "prate": "GPCPの降水", "z500": "再解析のZ500", "sst": "ERSSTv5の海面水温"}


def to_float(values):
    """GRIB の値を float32 にする。欠測（マスク）は NaN にする（海洋変数は陸が欠測。マスクを落とすと欠測値が値になる）。"""
    return np.ma.filled(np.ma.asarray(values).astype("float64"), np.nan).astype("float32")


def lead_of(msg, start_month):
    """メッセージのリード番号（1〜6）。validityDate は有効月の翌月1日。"""
    vm = (msg["validityDate"] // 100) % 100
    return (vm - start_month) % 12 or 12


def load(path, start_month):
    """GRIB を読む。戻り値: (配列[年, メンバー, リード, 緯, 経], lat, lon)。年は dataDate の年、予報は年1つ。"""
    cells = {}
    lat = lon = None
    for m in pygrib.open(path):
        y, mem, ld = m["dataDate"] // 10000, m["perturbationNumber"], lead_of(m, start_month)
        cells[(y, mem, ld)] = to_float(m.values)
        if lat is None:
            la, lo = m.latlons()
            lat, lon = la[:, 0], lo[0, :]
    years = sorted({k[0] for k in cells})
    mems = sorted({k[1] for k in cells})
    arr = np.full((len(years), len(mems), LEADS) + next(iter(cells.values())).shape, np.nan, dtype="float32")
    for (y, mem, ld), v in cells.items():
        if ld <= LEADS:
            arr[years.index(y), mems.index(mem), ld - 1] = v
    return arr, lat, lon


def period_fields(arr, leads):
    """リードのリスト（1始まり）を平均する。arr[..., リード, 緯, 経] → [..., 緯, 経]。"""
    idx = [k - 1 for k in leads]
    return arr[..., idx, :, :].mean(axis=-3)


def make_periods(start_month, n_years=None):
    """名前 -> (リードのリスト, 日本語ラベル)。リード1=初期月。"""
    def mon(k):
        return (start_month - 1 + k - 1) % 12 + 1
    p = {f"L{k}": ([k], f"{mon(k)}月の月平均") for k in range(1, LEADS + 1)}
    p["L2-4"] = ([2, 3, 4], f"{mon(2)}〜{mon(4)}月の3か月平均")
    p["L1-3"] = ([1, 2, 3], f"{mon(1)}〜{mon(3)}月の3か月平均")
    return p


def stats_for(F, H, leads):
    """期間の偏差・確率。F[メンバー,リード,緯,経]、H[年,メンバー,リード,緯,経]。"""
    f = period_fields(F, leads)                                   # [メンバー, 緯, 経]
    h = period_fields(H, leads).reshape(-1, *f.shape[1:])         # [年×メンバー, 緯, 経]
    mean = h.mean(0)
    t33, t67 = np.percentile(h, 100 / 3, axis=0), np.percentile(h, 200 / 3, axis=0)
    anom = f.mean(0) - mean
    up = (f > t67).mean(0).astype("float32")
    lo = (f < t33).mean(0).astype("float32")
    return dict(anom=anom.astype("float32"), p_upper=up, p_lower=lo, mean=mean.astype("float32"),
                t33=t33.astype("float32"), t67=t67.astype("float32"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--month", type=int, default=11)
    ap.add_argument("--hind", default="1993-2020")
    ap.add_argument("--vars", nargs="*", default=["t2m", "prate", "z500", "sst"])
    ap.add_argument("--periods", nargs="*", default=["L1", "L2", "L3", "L4", "L2-4"])
    ap.add_argument("--regions", nargs="*", default=list(charts.REGIONS))
    ap.add_argument("--alpha", type=float, default=None,
                    help="確率の縮小係数。未指定なら calibration.json（verify_cps4.py --write）の窓別の係数。--no-calib で未補正")
    ap.add_argument("--no-calib", action="store_true", help="縮小しない（生の確率）")
    a = ap.parse_args()
    os.makedirs(clim.DATA, exist_ok=True)
    periods = make_periods(a.month)
    name_of = {v[0]: k for k, v in VARS.items()}
    init = f"{a.year}{a.month:02d}01"
    for short in a.vars:
        cname = name_of[short]
        conv = VARS[cname][1]
        pf = os.path.join(C3S, f"jma_s4_{cname}_monthly_mean_{a.year}-{a.month:02d}_L1-6.grib")
        ph = os.path.join(C3S, f"jma_s4_{cname}_monthly_mean_{a.hind}-{a.month:02d}_L1-6.grib")
        F, lat, lon = load(pf, a.month)
        H, _, _ = load(ph, a.month)
        F, H = conv(F[0]), conv(H)                                    # F[メンバー,リード,緯,経]
        print(f"{short}: 予報{F.shape} ハインドキャスト{H.shape}", flush=True)
        out = {}
        for pname in a.periods:
            leads, label = periods[pname]
            s = stats_for(F, H, leads)
            out.update({f"{pname}_{k}": v for k, v in s.items()})
            vname = short                                                # charts.VARS のキー（t2m/prate/z500/sst）
            for rg in a.regions:
                path = os.path.join(charts.OUT, f"cps4_{init}_{short}_{pname}_{rg}.png")
                charts.render(vname, rg, s["anom"], s["p_upper"], s["p_lower"], F.shape[0], lat, lon, init=init,
                              label=label, out_path=path,
                              clim_text="JMA/MRI-CPS4 のハインドキャスト 1993–2020年（28年×10メンバー）",
                              member_text=f"JMA/MRI-CPS4（C3S経由）{F.shape[0]}メンバー（基準日{a.month}/1の前後31初期値のラグ）。",
                              alpha=(None if a.no_calib else (a.alpha if a.alpha is not None else charts.load_alpha(pname, rg, short, init, "cps4"))),
                              calib_basis=f"CPS4ハインドキャスト28年（10メンバー）と観測（{OBS_NAME[short]}）との照合",
                              alpha_scope=("" if charts.has_var_alpha(pname, short, init, "cps4") else "。2m気温の係数を仮に適用"),
                              title_text=f"JMA CPS4 {a.year}年{a.month}月1日基準",
                              extra_notes=COPERNICUS_NOTE.format(year=a.year),
                              source_text="JMA/MRI-CPS4（Copernicus C3S 経由）を加工して作成。気象庁・C3Sの推奨を示すものではない。")
                print("出力", os.path.relpath(path, clim.ROOT), flush=True)
        np.savez_compressed(os.path.join(clim.DATA, f"cps4_{init}_{short}.npz"), lat=lat, lon=lon, **out)


if __name__ == "__main__":
    main()
