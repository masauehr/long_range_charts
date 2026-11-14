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


DAILY_OBS = {   # 変数 -> (URLの相対パス, 保存名の前置き, nc変数名, 単位変換, 気圧面)
    "prate": ("ncep.reanalysis.dailyavgs/surface_gauss/prate.sfc.gauss.{y}.nc", "ncep_prate", "prate", lambda a: a * 86400.0, None),
    "z500": ("ncep.reanalysis.dailyavgs/pressure/hgt.{y}.nc", "ncep_hgt", "hgt", lambda a: a, 500),
}
DAILY_VI = {"t2m": 0, "prate": 1, "z500": 2}          # data/cfs_daily の変数の並び
MONTHLY_VI = {"t2m": 0, "prate": 1, "z500": 2, "pot5": 3}   # data/cfs_monthly の変数の並び


def load_obs_var(var, years):
    """変数別の日別観測 {年: (日付配列, 配列[日, 緯, 経])}。t2m は load_obs と同じ。降水は再解析（モデル由来で精度は低め）。"""
    if var == "t2m":
        return load_obs(years)
    rel, pre, vname, conv, level = DAILY_OBS[var]
    out, rg = {}, None
    for y in years:
        ds = xr.open_dataset(baseline_offset.fetch(f"{PSL}/{rel.format(y=y)}", f"{pre}.{y}.nc"))
        da = ds[vname] if level is None else ds[vname].sel(level=level)
        if rg is None:
            rg = fetch_daily.make_regrid(ds["lat"].values, ds["lon"].values)
        out[y] = (ds["time"].values.astype("datetime64[D]"), rg(conv(da.values.astype("float32"))))
    return out


def cases(target, years, window, vi=0):
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
            z = np.load(p)["arr"][:, :, vi]                      # [メンバー, 日, 緯, 経]（既定は t2m）
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


def evaluate(F, O, yr, off, years, ws):
    """1つの窓の照合。F[事例,メンバー,緯,経]・O[事例,緯,経]・yr/off[事例]。領域ごとの指標を返す。

    気候値は照合する年を除いた年抜き（予報側・観測側とも初期日のずれの回帰補正つき）。
    戻り値: {領域: dict(acc, acc_min, acc_max, bss_u, bss_l, alpha, bss_alpha)}
    """
    fs = F.reshape(-1, *F.shape[2:])                                         # メンバー展開
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
        valid = (np.isfinite(cf["mean"]) & np.isfinite(co["mean"]))[None]      # 予報か観測が欠測の格子（陸・海）は除く
        for k in BOXES:
            for i in range(te.sum()):
                acc[k][y].append(wcorr(AF[i], AO[i], ws[k]))
            w = ws[k][None] * valid
            bs[k]["fu"] += float(np.sum(w * (pu - ou) ** 2))
            bs[k]["fl"] += float(np.sum(w * (pl - ol) ** 2))
            bs[k]["cu"] += float(np.sum(w * (1 / 3 - ou) ** 2))
            bs[k]["cl"] += float(np.sum(w * (1 / 3 - ol) ** 2))
            # 確率を気候値(1/3)へ縮める p'=1/3+α(p-1/3) の最適 α を求めるための和（BS(α) は α の2次式）
            bs[k]["Au"] += float(np.sum(w * (pu - 1 / 3) ** 2))
            bs[k]["Bu"] += float(np.sum(w * (pu - 1 / 3) * (1 / 3 - ou)))
            bs[k]["Al"] += float(np.sum(w * (pl - 1 / 3) ** 2))
            bs[k]["Bl"] += float(np.sum(w * (pl - 1 / 3) * (1 / 3 - ol)))
    out = {}
    for k in BOXES:
        per_year = np.array([np.mean(acc[k][y]) for y in years])
        b = bs[k]
        al = float(np.clip(-(b["Bu"] + b["Bl"]) / (b["Au"] + b["Al"]), 0, 1))
        c_all = b["cu"] + b["cl"]
        bs_a = c_all + 2 * al * (b["Bu"] + b["Bl"]) + al ** 2 * (b["Au"] + b["Al"])
        out[k] = dict(acc_year={int(y): float(np.mean(acc[k][y])) for y in years},
                      acc=float(per_year.mean()), acc_min=float(per_year.min()), acc_max=float(per_year.max()),
                      bss_u=1 - b["fu"] / b["cu"], bss_l=1 - b["fl"] / b["cl"], alpha=al, bss_alpha=1 - bs_a / c_all)
    return out


def obs_month(obs, year, month, start_day=1):
    """観測の暦月平均（start_day 以降）。"""
    t, a = obs[year]
    s = np.datetime64(dt.date(year, month, start_day))
    e = np.datetime64(dt.date(year + month // 12, month % 12 + 1, 1))
    sel = np.where((t >= s) & (t < e))[0]
    return a[sel].mean(0)


def monthly_cases(target, years, window, vi=0):
    """月平均ファイル(cfs_monthly)の事例。同じ月の初期日だけ（リードを暦月でそろえるため）。"""
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    out = []
    for y in years:
        anchor = dt.date(y, t.month, min(t.day, 28)) + dt.timedelta(days=max(t.day - 28, 0))
        for d in range(-window, window + 1):
            day = anchor + dt.timedelta(days=d)
            if day.month != t.month:
                continue
            p = os.path.join(clim.CF_DIR, day.strftime("%Y%m%d") + ".npz")
            if os.path.exists(p):
                out.append((y, d, day, np.load(p)["arr"][:, :4, vi]))       # [メンバー, リード0〜3, 緯, 経]（既定は t2m）
    return out


def monthly_windows():
    """L2の期間: 名前 -> リードのリスト（charts.PERIODS と同じ）。"""
    import charts
    return {k: v for k, v in charts.PERIODS.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--years", default="2019-2025")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--monthly-window", type=int, default=15, help="月平均(L2)の照合で使う初期日の前後日数")
    ap.add_argument("--write", action="store_true", help="縮小係数を calibration.json に書き出す")
    a = ap.parse_args()
    y0, _, y1 = a.years.partition("-")
    years = list(range(int(y0), int(y1 or y0) + 1))
    obs = load_obs(years + [years[-1] + 1])
    ws = {k: weights(b) for k, b in BOXES.items()}
    rows = []
    # --- 日別（L1）: 週1〜4と28日
    xs, meta = cases(a.target, years, a.window)
    print(f"日別の事例 {len(meta)}（年×初期日。メンバー4）。年 {years}", flush=True)
    yr = np.array([m[0] for m in meta])
    off = np.array([float(m[1]) for m in meta])
    for name, span in {**weekly.WEEKS, "J28": weekly.JMA_WINDOWS["J28"]}.items():
        F = np.stack([z[:, span[0] - 1:span[1]].mean(1) for z in xs])
        O = np.stack([obs_window(obs, m[2], span) for m in meta])
        rows.append((name, evaluate(F, O, yr, off, years, ws)))
    # --- 月平均（L2）: M1〜M4・Q1（暦月。リード0は初期日以降の部分月）
    mc = monthly_cases(a.target, years, a.monthly_window)
    print(f"月平均の事例 {len(mc)}（同月の初期日のみ）", flush=True)
    myr = np.array([m[0] for m in mc])
    moff = np.array([float(m[1]) for m in mc])
    for name, leads in monthly_windows().items():
        F = np.stack([m[3][:, leads].mean(1) for m in mc])
        Ol = []
        for (y, d, day, _) in mc:
            vals = []
            for k in leads:
                mi = day.month - 1 + k
                vals.append(obs_month(obs, day.year + mi // 12, mi % 12 + 1, day.day if k == 0 else 1))
            Ol.append(np.mean(vals, 0))
        rows.append((name, evaluate(F, np.stack(Ol), myr, moff, years, ws)))
    print("\n| 窓 | 領域 | ACC(年平均) | ACCの年ごとの範囲 | BSS上位1/3 | BSS下位1/3 | 最適な縮小係数α | α適用後のBSS(上下合計) |")
    print("|---|---|---|---|---|---|---|---|")
    for name, r in rows:
        for k, v in r.items():
            print(f"| {name} | {k} | {v['acc']:+.2f} | {v['acc_min']:+.2f}〜{v['acc_max']:+.2f} | {v['bss_u']:+.2f} | "
                  f"{v['bss_l']:+.2f} | {v['alpha']:.2f} | {v['bss_alpha']:+.2f} |")
    if a.write:
        import calib
        calib.update_cfs(
            a.target,
            meta={"作成日": dt.date.today().isoformat(), "年": years,
                  "方法": "verify.py: 2m気温を再解析(NCEP/NCAR)と照合・年抜き・BSSが最良になる縮小係数 p'=1/3+α(p-1/3)",
                  "注意": "独立な年は7つ。αは同じ事例で当てており過学習ぎみ。2m気温の係数を他の変数にも仮に適用。"},
            alpha={n: {"asia": round(r["東アジア"]["alpha"], 2), "global": round(r["全球"]["alpha"], 2),
                       "acc_asia": round(r["東アジア"]["acc"], 2), "acc_global": round(r["全球"]["acc"], 2)} for n, r in rows})
        print("書き出し: calibration.json")


if __name__ == "__main__":
    main()
