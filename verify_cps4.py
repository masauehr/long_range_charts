"""C3S の JMA CPS4 のハインドキャスト（1993–2020・28年×10メンバー）を、観測（NCEP/NCAR 再解析の月平均2m気温）と照合する。

verify.py の evaluate を使う（気候値は照合する年を除いた年抜き・指標は ACC と三分位確率の BSS・縮小係数 α）。
- 事例=28年（基準日11/1の1回/年）。メンバー=10（予報本番の155メンバーより少ない。本番はラグで多いぶん確率の標本誤差が小さい）。
- 強いEl Niño年（1997・2015）とそれ以外で ACC を分けて見る（ハインドキャストに強い年が2つ入っている）。
- 観測は再解析（観測そのものではない）。2m気温だけ（降水・Z500・SST は未照合）。
使い方: python verify_cps4.py [--write]   # --write で calibration.json に CPS4 の係数 L1〜L6, L2-4, L1-3 を追記（CFS分は残す）
"""
import argparse
import json
import os

import numpy as np

import clim
import cps4
import verify

START_MONTH = 11
YEARS = list(range(1993, 2021))
STRONG_EL_NINO = [1997, 2015]
WINDOWS = {"L1": [1], "L2": [2], "L3": [3], "L4": [4], "L5": [5], "L6": [6], "L2-4": [2, 3, 4], "L1-3": [1, 2, 3]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    path = os.path.join(cps4.C3S, f"jma_s4_2m_temperature_monthly_mean_1993-2020-{START_MONTH:02d}_L1-6.grib")
    arr, lat, lon = cps4.load(path, START_MONTH)                       # [年, メンバー, リード, 緯, 経]
    conv = cps4.VARS["2m_temperature"][1]
    H = conv(arr)[..., ::2, ::2]                                       # 1.25°→2.5°（verify の格子と同じ）
    assert H.shape[-2:] == (len(verify.LAT), len(verify.LON)), H.shape
    obs = verify.load_obs(YEARS + [YEARS[-1] + 1])
    ws = {k: verify.weights(b) for k, b in verify.BOXES.items()}
    yr = np.array(YEARS)
    off = np.zeros(len(YEARS))
    print(f"ハインドキャスト {H.shape}（年, メンバー, リード, 緯, 経）。事例{len(YEARS)}年", flush=True)
    rows = []
    for name, leads in WINDOWS.items():
        F = H[:, :, [k - 1 for k in leads]].mean(axis=2)               # [年, メンバー, 緯, 経]
        O = []
        for y in YEARS:
            v = []
            for k in leads:
                mi = START_MONTH - 1 + k - 1
                v.append(verify.obs_month(obs, y + mi // 12, mi % 12 + 1))
            O.append(np.mean(v, 0))
        rows.append((name, verify.evaluate(F, np.stack(O), yr, off, YEARS, ws)))
    print("\n| 窓 | 領域 | ACC(年平均) | ACCの年ごとの範囲 | ACC 強いEl Niño年(1997・2015) | ACC それ以外 | BSS上位1/3 | BSS下位1/3 | 最適α | α適用後BSS |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in rows:
        for k, v in r.items():
            en = np.mean([v["acc_year"][y] for y in STRONG_EL_NINO])
            ot = np.mean([x for y, x in v["acc_year"].items() if y not in STRONG_EL_NINO])
            print(f"| {name} | {k} | {v['acc']:+.2f} | {v['acc_min']:+.2f}〜{v['acc_max']:+.2f} | {en:+.2f} | {ot:+.2f} | "
                  f"{v['bss_u']:+.2f} | {v['bss_l']:+.2f} | {v['alpha']:.2f} | {v['bss_alpha']:+.2f} |")
    if a.write:
        p = os.path.join(clim.ROOT, "calibration.json")
        cal = json.load(open(p, encoding="utf-8"))
        cal["メタ_CPS4"] = {"方法": "verify_cps4.py: CPS4ハインドキャスト1993–2020(28年×10メンバー)を再解析の月平均2m気温と照合・年抜き・BSS最良の縮小係数",
                          "注意": "事例は28年。ハインドキャストは10メンバーで、本番の155メンバー(ラグ)より少ない。2m気温の係数を他の変数にも仮に適用。"}
        for name, r in rows:
            cal["alpha"][name] = {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                                  "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
        print("追記: calibration.json")


if __name__ == "__main__":
    main()
