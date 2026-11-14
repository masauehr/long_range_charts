"""CFSv2 の予報（本プロジェクトの図）と、気象庁の1か月予報（気温）を地域ごとに見比べる。

気象庁の値は reference/jma_1month_*.json に手で保存したもの（JMA MCP の結果）。
定義の違いに注意:
  気象庁: 平年は 1991–2020 年の平年値。確率は「平年以上/以下」。
  本図 : 気候値は CFSv2 運用予報の 2019–2025（約7年）。確率は上位1/3、および「気候値の平均を超える割合」。
CFS の格子は 2.5° のため、地域の代表点へ双一次補間した値で比べる（地域平均ではない）。
使い方: python compare_jma.py --target 20261112 --ref reference/jma_1month_20261111.json
"""
import argparse
import json
import os

import numpy as np
from scipy.interpolate import RegularGridInterpolator

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
    ap.add_argument("--lead", type=int, default=0, help="比べる30日ブロック（既定0=初期日から1〜30日）")
    a = ap.parse_args()
    ref = json.load(open(a.ref, encoding="utf-8"))
    c = np.load(os.path.join(clim.DATA, f"clim_{a.target[4:]}.npz"))
    z = np.load(os.path.join(clim.CF_DIR, f"{a.target}.npz"))["arr"][:, a.lead, 0]      # [メンバー, 緯, 経] 2m気温
    lat, lon = c["lat"], c["lon"]
    mean, t33, t67 = (c[k][a.lead, 0] for k in ("mean", "t33", "t67"))
    print(f"{ref['対象']}（気象庁 初期値{ref['初期値日']}）と CFSv2 {a.target} 00Z のブロック{a.lead}を比較")
    print("| 地域 | 気象庁 平年差 | 気象庁 高い確率 | CFS 偏差(気候値比) | CFS 上位1/3の確率 | CFS 平均超えの割合 | メンバー平均値(℃) |")
    print("|---|---|---|---|---|---|---|")
    for name, d in ref["地域"].items():
        pt = d["点"]
        m = at_point(z, lat, lon, pt)                  # メンバーごとの値
        mu, hi, lo_ = (float(at_point(f, lat, lon, pt)) for f in (mean, t67, t33))
        print(f"| {name} | {d['平年差']:+.1f}℃ | {d['高い確率']}% | {np.mean(m) - mu:+.1f}℃ | "
              f"{np.mean(m > hi) * 100:.0f}% | {np.mean(m > mu) * 100:.0f}% | {np.mean(m):.1f} |")


if __name__ == "__main__":
    main()
