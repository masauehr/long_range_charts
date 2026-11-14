"""CFSv2 の予報と、気象庁の1か月予報（気温）を、同じ期間・地域で見比べる。

気象庁の値は reference/jma_1month_*.json（JMA MCP の結果を手で保存）。期間は日数でそろえる:
  初期日 2026-11-12（=予報1日目）。気象庁の対象期間 11/14〜 は予報3日目から。窓名 J28/J1/J2/J34 は weekly.py と共通。
定義の違い:
  気象庁: 平年=1991–2020。確率は「平年以上/以下」。
  本図 : 気候値=CFSv2運用予報2019–2025（約7年）。確率は上位1/3、および「気候値の平均を超えるメンバーの割合」。
  基準の差の見積もり: 再解析(NCEP/NCAR)の同期間の「2019–2025平均−1991–2020平年」(baseline_offset.py)を CFS偏差に足した値も併記。
CFSの格子は2.5°のため、地域の代表点へ双一次補間した値で比べる（地域平均ではない）。メンバーは00Zの4つ。
使い方: python compare_jma.py --target 20261112 --ref reference/jma_1month_20261111.json
"""
import argparse
import json
import os

import numpy as np
from scipy.interpolate import RegularGridInterpolator

import baseline_offset
import clim


def at_point(field, lat, lon, pt):
    """[..., 緯, 経] の場を代表点へ補間する（緯度は北→南、経度は0〜357.5を巻き込む）。"""
    f = np.concatenate([field, field[..., :1]], axis=-1)
    lo = np.concatenate([lon, [360.0]])
    itp = RegularGridInterpolator((lat[::-1], lo), f[..., ::-1, :].transpose(-2, -1, *range(f.ndim - 2)),
                                  bounds_error=False, fill_value=None)
    return itp((pt[0], pt[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--years", default="2019-2025")
    a = ap.parse_args()
    ref = json.load(open(a.ref, encoding="utf-8"))
    w = np.load(os.path.join(clim.DATA, f"weekly_{a.target}.npz"))
    lat, lon = w["lat"], w["lon"]
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    pts = {n: d["点"] for n, d in ref["地域"].items()}
    print(f"気象庁 1か月予報（初期値{ref['初期値日']}・気温）と CFSv2 {a.target} 00Z（メンバー{w['J28_members'].shape[0]}）")
    print("| 期間 | 地域 | 気象庁 平年差 | 気象庁 高い確率 | CFS 偏差(2019–25比) | 再解析の基準差 | CFS偏差+基準差 | CFS 上位1/3の確率 | CFS 平均超えの割合 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for k, win in ref["期間"].items():
        off = baseline_offset.offsets(pts, win["開始"], win["日数"], years)
        mem, mean, t67 = w[f"{k}_members"][:, 0], w[f"{k}_mean"][0], w[f"{k}_t67"][0]     # 変数0=t2m
        for name, d in ref["地域"].items():
            pt = d["点"]
            m = at_point(mem, lat, lon, pt)
            mu, hi = float(at_point(mean, lat, lon, pt)), float(at_point(t67, lat, lon, pt))
            an = float(np.mean(m)) - mu
            j = d["予報"][k]
            print(f"| {k}（{win['開始']}〜{win['日数']}日） | {name} | {j['平年差']:+.1f}℃ | {j['高い確率']}% | {an:+.1f}℃ | "
                  f"{off[name][0]:+.2f}℃ | {an + off[name][0]:+.1f}℃ | {np.mean(m > hi) * 100:.0f}% | {np.mean(m > mu) * 100:.0f}% |")


if __name__ == "__main__":
    main()
