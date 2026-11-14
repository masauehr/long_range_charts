"""CFSv2 の予報（2m気温）を、過去の観測（NCEP/NCAR 再解析の2m気温）と照合する。

予報: data/cfs_daily/（2019–2025・対象日の前後 window 日の初期日・00Zの4メンバー・先頭30日の日平均）。
観測: NOAA PSL の NCEP/NCAR 再解析（baseline_offset.py で取得済みの data/ref_psl/ の日別2m気温）。再解析は観測そのもの
      ではない（モデル出力を含む）。降水・Z500 は同様の再解析を用意していないため、2m気温だけ。
気候値: **照合する年を除いた「年抜き」**で、予報側・観測側とも同じ手順（初期日のずれの回帰補正）で作る。
指標（窓ごと）:
  ACC  : 予報の偏差と観測の偏差の空間相関（面積重み・領域内で中心化）。事例=(年, 初期日のずれ)
  BSS  : 上位/下位三分位の確率予報のブライアスキルスコア（気候値=1/3を基準。正なら気候値より良い）
注意: 独立な年は7つだけ（同じ年の初期日どうしは強く相関する）。結果は参考程度で、信頼性図は作れない。
使い方: python verify.py --target 20261112
"""
import argparse
import datetime as dt
import glob
import os

import numpy as np
import xarray as xr

import baseline_offset
import clim
import fetch_daily
import weekly

PSL = baseline_offset.PSL
LAT, LON = fetch_daily.LAT, fetch_daily.LON
BOXES = {
    "全球": (-90, 90, 0, 360),
    "東アジア": (20, 60, 100, 160),
}


def load_obs(years):
    """年ごとの日別2m気温(℃)を 2.5° 格子へ。戻り値: {年: (日付配列[datetime64[D]], 配列[日, 緯, 経])}。"""
    out = {}
    rg = None
    for y in years:
        p = baseline_offset.fetch(f"{PSL}/ncep.reanalysis.dailyavgs/surface_gauss/air.2m.gauss.{y}.nc",
                                  f"air.2m.gauss.{y}.nc")
        ds = xr.open_dataset(p)["air"]
        if rg is None:
            rg = fetch_daily.make_regrid(ds["lat"].values, ds["lon"].values)
        out[y] = (ds["time"].values.astype("datetime64[D]"), rg(ds.values.astype("float32") - 273.15))
    return out


def obs_window(obs, day, span):
    """初期日 day（date）から数えた窓 span=(開始日,終了日) の観測平均。"""
    t, a = obs[day.year]
    s = np.datetime64(day + dt.timedelta(days=span[0] - 1))
    e = np.datetime64(day + dt.timedelta(days=span[1] - 1))
    sel = np.where((t >= s) & (t <= e))[0]
    assert len(sel) == span[1] - span[0] + 1, (day, span)
    return a[sel].mean(0)


def cases(target, years, window):
    """予報サンプル（メンバー展開）と、各サンプルの (年, ずれ日数, 初期日) を返す。weekly.load_daily と同じ順序。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    xs, meta = [], []
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            p = os.path.join(weekly.DAILY, day.strftime("%Y%m%d") + ".npz")
            if not os.path.exists(p):
                continue
            z = np.load(p)["arr"][:, :, 0]                       # [メンバー, 日, 緯, 経]（t2m）
            xs.append(z)
            meta.append((y, d, day))
    return xs, meta


def weights(box):
    w = np.cos(np.deg2rad(LAT))[:, None] * np.ones(len(LON))[None, :]
    la, lo = np.meshgrid(LAT, LON, indexing="ij")
    m = (la >= box[0]) & (la <= box[1]) & (lo >= box[2]) & (lo <= box[3])
    return w * m


def wcorr(a, b, w):
    ok = np.isfinite(a) & np.isfinite(b) & (w > 0)
    ww = w[ok]
    a, b = a[ok], b[ok]
    a = a - np.sum(ww * a) / ww.sum()
    b = b - np.sum(ww * b) / ww.sum()
    return float(np.sum(ww * a * b) / np.sqrt(np.sum(ww * a * a) * np.sum(ww * b * b)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    xs, meta = cases(a.target, years, a.window)
    obs = load_obs(years)
    wins = {**weekly.WEEKS, "J28": weekly.JMA_WINDOWS["J28"]}
    ws = {k: weights(b) for k, b in BOXES.items()}
    print(f"事例 {len(meta)}（年×初期日。メンバー4）。年 {years}")
    rows = []
    for name, span in wins.items():
        s0, s1 = span
        F = np.stack([z[:, s0 - 1:s1].mean(1) for z in xs])                 # [事例, メンバー, 緯, 経]
        O = np.stack([obs_window(obs, m[2], span) for m in meta])           # [事例, 緯, 経]
        yr = np.array([m[0] for m in meta])
        off = np.array([float(m[1]) for m in meta])
        fs = F.reshape(-1, *F.shape[2:])                                     # メンバー展開
        fyr, foff = np.repeat(yr, F.shape[1]), np.repeat(off, F.shape[1])
        acc = {k: {y: [] for y in years} for k in BOXES}
        bs = {k: {"fu": 0.0, "fl": 0.0, "cu": 0.0, "cl": 0.0, "Au": 0.0, "Bu": 0.0, "Al": 0.0, "Bl": 0.0} for k in BOXES}
        for y in years:
            tr, te = yr != y, yr == y
            cf = clim.make_clim(fs[fyr != y], foff[fyr != y])
            co = clim.make_clim(O[tr], off[tr])
            Fa = F[te] - cf["slope"][None, None] * off[te][:, None, None, None]
            Oa = O[te] - co["slope"][None] * off[te][:, None, None]
            AF = Fa.mean(1) - cf["mean"]
            AO = Oa - co["mean"]
            pu = (Fa > cf["t67"]).mean(1)
            pl = (Fa < cf["t33"]).mean(1)
            ou, ol = (Oa > co["t67"]).astype(float), (Oa < co["t33"]).astype(float)
            for k in BOXES:
                for i in range(te.sum()):
                    acc[k][y].append(wcorr(AF[i], AO[i], ws[k]))
                w = ws[k][None]
                bs[k]["fu"] += float(np.sum(w * (pu - ou) ** 2))
                bs[k]["fl"] += float(np.sum(w * (pl - ol) ** 2))
                bs[k]["cu"] += float(np.sum(w * (1 / 3 - ou) ** 2))
                bs[k]["cl"] += float(np.sum(w * (1 / 3 - ol) ** 2))
                # 確率を気候値(1/3)へ縮める p'=1/3+α(p-1/3) の最適 α を求めるための和（BS(α) は α の2次式）
                bs[k]["Au"] += float(np.sum(w * (pu - 1 / 3) ** 2))
                bs[k]["Bu"] += float(np.sum(w * (pu - 1 / 3) * (1 / 3 - ou)))
                bs[k]["Al"] += float(np.sum(w * (pl - 1 / 3) ** 2))
                bs[k]["Bl"] += float(np.sum(w * (pl - 1 / 3) * (1 / 3 - ol)))
        for k in BOXES:
            per_year = np.array([np.mean(acc[k][y]) for y in years])
            b = bs[k]
            # 最適な縮小係数 α*（0〜1に制限）と、そのときのBSS
            au = float(np.clip(-(b["Bu"] + b["Bl"]) / (b["Au"] + b["Al"]), 0, 1))
            c_all = b["cu"] + b["cl"]
            bs_a = c_all + 2 * au * (b["Bu"] + b["Bl"]) + au ** 2 * (b["Au"] + b["Al"])
            rows.append((name, k, per_year.mean(), per_year.min(), per_year.max(),
                         1 - b["fu"] / b["cu"], 1 - b["fl"] / b["cl"], au, 1 - bs_a / c_all))
    print("\n| 窓 | 領域 | ACC(年平均) | ACCの年ごとの範囲 | BSS上位1/3 | BSS下位1/3 | 最適な縮小係数α | α適用後のBSS(上下合計) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]:+.2f} | {r[3]:+.2f}〜{r[4]:+.2f} | {r[5]:+.2f} | {r[6]:+.2f} | {r[7]:.2f} | {r[8]:+.2f} |")


if __name__ == "__main__":
    main()
