"""エルニーニョ監視: NINO.3 / NINO.3.4 の海面水温偏差の推移（観測）と、JMA/MRI-CPS4 の予測の束・確率。

- 観測: NOAA ERSSTv5（NOAA PSL）の月平均海面水温。**気象庁の公式の監視（COBE-SST2・気象庁の基準）とは別のデータ**なので、数値は少し違う。
  - NINO.3（5°S–5°N・150°W–90°W）: **気象庁の指標**。基準値は「前年までの30年平均」（気象庁と同じ考え方）。5か月移動平均で現象を判定する。
  - NINO.3.4（5°S–5°N・170°W–120°W）: **NOAA の従来の ONI 方式**（基準は 1991〜2020年平均・3か月移動平均）。国際的に広く使われてきたが、
    NOAA/CPC は 2026年2月から公式の指標を **RONI**（NINO.3.4 偏差から熱帯全体 20°S–20°N の平均偏差を引き、分散をそろえたもの）に切り替えた。
    RONI も ERSSTv5 から計算して併記する（CPC の公式値と小さな差が出うる）。
- 予測: CPS4 の海面水温（予報155メンバー）を、ハインドキャスト1993–2020のモデル気候値からの偏差にする。偏差が +0.5℃以上／−0.5℃以下の
  メンバーの割合を、エルニーニョ側／ラニーニャ側の確率として示す。過去28年の予測技能（ACC）も添える。
- 気象庁の公式の見通し（ローカルのみ）は reference/jma_elnino_YYYYMM.json（監視速報の要約・出典リンク。手動で更新）。公開サイトには載せない。

使い方: python enso.py --year 2026 --month 11        # 観測の図＋CPS4（2026年11月基準）の予測の図＋ web/enso.json
        python enso.py --obs-only                       # 観測の図だけ
"""
import argparse
import datetime as dt
import glob
import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd
import xarray as xr

import baseline_offset
import charts                      # 日本語フォント・Agg の設定を引き継ぐ
import clim
import cps4
import matplotlib.pyplot as plt

ROOT = clim.ROOT
OUT = charts.OUT
WEB = os.path.join(ROOT, "web")
REF = os.path.join(ROOT, "reference")
ERSST_URL = f"{baseline_offset.PSL}/noaa.ersst.v5/sst.mnmean.nc"
ERSST_NAME = "ersst_v5_sst.mnmean.nc"
# 領域: キー -> (名前, 南緯, 北緯, 西経度(東経0〜360), 東経度)
BOX = {"nino3": ("NINO.3", -5, 5, 210, 270), "nino34": ("NINO.3.4", -5, 5, 190, 240), "trop": ("熱帯平均(20°S–20°N)", -20, 20, 0, 360)}
LABEL = {"nino3": "気象庁の指標", "nino34": "NOAAの従来のONI方式"}
THRESH = 0.5                       # エルニーニョ/ラニーニャ側とみなす偏差（℃）
NOTE_OBS = "NOAA ERSSTv5（NOAA PSL）の月平均海面水温から作成。気象庁の公式の監視（COBE-SST2・気象庁の基準）とは別のデータで、数値が最大0.5℃ほど違うことがある。気象庁の公式情報ではない。"


# ------------------------------------------------------------------ 共通
def region_mean(a, lat, lon, box):
    """a[..., 緯, 経] の領域平均（cos緯度の重み・欠測は除く）。"""
    _, la0, la1, lo0, lo1 = box
    ym = (lat >= la0) & (lat <= la1)
    xm = (lon >= lo0) & (lon <= lo1)
    sub = a[..., ym, :][..., :, xm]
    w = np.cos(np.deg2rad(lat[ym]))[:, None] * np.ones(int(xm.sum()))[None, :]
    ok = np.isfinite(sub)
    num = np.sum(np.where(ok, sub, 0.0) * w, axis=(-2, -1))
    den = np.sum(ok * w, axis=(-2, -1))
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)


def ensure_ersst(max_age_days=20):
    """ERSSTv5 の月平均ファイル（約160MB）。無い・古いときは取り直す（毎月更新されるため）。"""
    os.makedirs(baseline_offset.D_DIR, exist_ok=True)
    p = os.path.join(baseline_offset.D_DIR, ERSST_NAME)
    if (not os.path.exists(p)) or (time.time() - os.path.getmtime(p) > max_age_days * 86400):
        tmp = p + ".tmp"
        with urllib.request.urlopen(ERSST_URL, timeout=300) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(tmp, p)                                      # 書き終えてから置き換える
    return p


def month_label(y, m):
    return f"{y}-{m:02d}"


# ------------------------------------------------------------------ 観測
def load_obs():
    """ERSSTv5 → {キー: pandas.Series（月初の日付→領域平均SST℃）}。"""
    ds = xr.open_dataset(ensure_ersst(), drop_variables=["time_bnds"])
    sst = ds["sst"].values.astype("float64")
    lat, lon = ds["lat"].values, ds["lon"].values
    idx = pd.to_datetime(ds["time"].values).to_period("M").to_timestamp()
    return {k: pd.Series(region_mean(sst, lat, lon, b), index=idx) for k, b in BOX.items()}


def sliding30_anomaly(s):
    """気象庁の考え方: 各年月の偏差 = その値 − 前年までの30年の同じ月の平均。"""
    out = pd.Series(np.nan, index=s.index)
    tab = s.groupby([s.index.month, s.index.year]).first()
    for t in s.index:
        base = [tab.get((t.month, y), np.nan) for y in range(t.year - 30, t.year)]
        if np.isfinite(base).sum() >= 25:
            out[t] = s[t] - np.nanmean(base)
    return out


def fixed_anomaly(s, y0=1991, y1=2020):
    """NOAA の従来（ONI）の考え方: 偏差 = その値 − 1991〜2020年の同じ月の平均。"""
    clim_m = s[(s.index.year >= y0) & (s.index.year <= y1)].groupby(lambda t: t.month).mean()
    return s - s.index.month.map(clim_m).values


def obs_anomalies(obs):
    """{キー: dict(anom=月偏差, ma=移動平均, ma_n=移動平均の月数, base=基準の説明)}。"""
    a3 = sliding30_anomaly(obs["nino3"])
    a34 = fixed_anomaly(obs["nino34"])
    roni = relative_index(a34, fixed_anomaly(obs["trop"]))
    return {"nino3": dict(anom=a3, ma=a3.rolling(5, center=True, min_periods=5).mean(), ma_n=5, base="前年までの30年平均（気象庁の考え方）"),
            "nino34": dict(anom=a34, ma=a34.rolling(3, center=True, min_periods=3).mean(), ma_n=3, base="1991〜2020年平均（NOAAの従来のONI方式）"),
            "roni": dict(anom=roni, ma=roni.rolling(3, center=True, min_periods=3).mean(), ma_n=3, base="NINO.3.4偏差−熱帯平均偏差（分散をそろえる）")}


def relative_index(a34, atrop, y0=1991, y1=2020):
    """RONI（相対的な NINO.3.4）: NINO.3.4 偏差から熱帯全体（20°S–20°N）の平均偏差を引き、分散が元の NINO.3.4 偏差と同じになるよう係数を掛ける。
    係数は 1991〜2020年の標準偏差の比。CPC の公式値と小さな差が出うる（本ツールの再現）。"""
    rel = a34 - atrop
    base = (a34.index.year >= y0) & (a34.index.year <= y1)
    k = float(np.nanstd(a34[base]) / np.nanstd(rel[base]))
    return rel * k


def state_text(an):
    """直近の状態の目安（ERSSTv5による。公式判定ではない）。"""
    a = an["nino3"]["anom"].dropna()
    last = a.index[-1]
    ma = a.iloc[-5:].mean()
    r = an["roni"]["anom"].dropna() if "roni" in an else None
    if ma >= THRESH:
        kind = "エルニーニョ側"
    elif ma <= -THRESH:
        kind = "ラニーニャ側"
    else:
        kind = "平常（どちらでもない）"
    strong = "（非常に強い）" if ma >= 2.0 else "（強い）" if ma >= 1.5 else ""
    extra = f"。RONI {r.iloc[-1]:+.1f}℃（NOAAの現在の公式指標。{month_label(r.index[-1].year, r.index[-1].month)}）" if r is not None and len(r) else ""
    return dict(kind=kind + strong, last_month=month_label(last.year, last.month), last_value=round(float(a.iloc[-1]), 2),
                trailing5=round(float(ma), 2), roni_last=None if r is None or not len(r) else round(float(r.iloc[-1]), 2),
                text=f"{month_label(last.year, last.month)} の NINO.3 偏差 {a.iloc[-1]:+.1f}℃・直近5か月平均 {ma:+.1f}℃ → {kind}{strong}{extra}（ERSSTv5による目安・公式判定ではない）")


# ------------------------------------------------------------------ CPS4 の予測
def cps4_forecast(year, month, obs, an):
    """CPS4（予報155メンバー・ハインドキャスト28年）から、NINO領域の偏差の予測と確率、過去28年の技能(ACC)を作る。"""
    cname = "sea_surface_temperature"
    pf = os.path.join(cps4.C3S, f"jma_s4_{cname}_monthly_mean_{year}-{month:02d}_L1-6.grib")
    ph = os.path.join(cps4.C3S, f"jma_s4_{cname}_monthly_mean_1993-2020-{month:02d}_L1-6.grib")
    F, lat, lon = cps4.load(pf, month)
    H, _, _ = cps4.load(ph, month)
    conv = cps4.VARS[cname][1]
    F, H = conv(F[0]), conv(H)                                    # F[メンバー,リード,緯,経]  H[年,メンバー,リード,緯,経]
    years = list(range(1993, 1993 + H.shape[0]))
    res = {}
    for k, box in BOX.items():
        f = region_mean(F, lat, lon, box)                         # [メンバー, リード]
        h = region_mean(H, lat, lon, box)                         # [年, メンバー, リード]
        cl = np.nanmean(h, axis=(0, 1))                           # モデル気候値（リードごと）
        fa = f - cl[None, :]
        ha = np.nanmean(h, axis=1) - cl[None, :]                  # ハインドキャストのアンサンブル平均偏差 [年, リード]
        s = obs[k]
        acc = []
        for ld in range(f.shape[1]):
            mi = month - 1 + ld
            o = []
            for y in years:
                t = pd.Timestamp(y + mi // 12, mi % 12 + 1, 1)
                o.append(s.get(t, np.nan))
            o = np.array(o)
            base = np.array([s.get(pd.Timestamp(y + mi // 12, mi % 12 + 1, 1), np.nan) for y in years])
            oa = o - np.nanmean(base)
            ok = np.isfinite(oa) & np.isfinite(ha[:, ld])
            acc.append(float(np.corrcoef(oa[ok], ha[ok, ld])[0, 1]) if ok.sum() > 5 else None)
        leads = f.shape[1]
        months = []
        for ld in range(leads):
            mi = month - 1 + ld
            months.append(month_label(year + mi // 12, mi % 12 + 1))
        res[k] = dict(months=months, members=fa, mean=np.nanmean(fa, 0), p10=np.nanpercentile(fa, 10, 0), p90=np.nanpercentile(fa, 90, 0),
                      p_el=np.nanmean(fa >= THRESH, 0), p_la=np.nanmean(fa <= -THRESH, 0), acc=acc, n=fa.shape[0])
    return res


# ------------------------------------------------------------------ 図
def _foot(fig, lines):
    fig.text(0.01, 0.012, "\n".join(lines), fontsize=8, color="#444444", va="bottom", ha="left", linespacing=1.5)


def plot_obs(an, path, months=36):
    fig, axes = plt.subplots(2, 1, figsize=(12, 8.2), sharex=True)
    for ax, k in zip(axes, ("nino3", "nino34")):
        a = an[k]["anom"].dropna().iloc[-months:]
        ma = an[k]["ma"].reindex(a.index)
        ax.bar(a.index, a.values, width=24, color=np.where(a.values >= 0, "#d6604d", "#4393c3"), alpha=0.75, label="月偏差")
        ax.plot(ma.index, ma.values, color="black", lw=2, label=f"{an[k]['ma_n']}か月移動平均")
        if k == "nino34" and "roni" in an:
            rm = an["roni"]["ma"].reindex(a.index)
            ax.plot(rm.index, rm.values, color="#2166ac", lw=2, ls="--", label="RONI（3か月移動平均・NOAAが2026年2月から公式）")
        ax.axhline(THRESH, color="#b2182b", ls="--", lw=1)
        ax.axhline(-THRESH, color="#2166ac", ls="--", lw=1)
        ax.axhline(0, color="#666666", lw=0.8)
        ax.set_ylabel("偏差（℃）")
        ax.set_title(f"{BOX[k][0]} の海面水温偏差（基準: {an[k]['base']}）" + ("　［気象庁の指標］" if k == "nino3" else "　［NOAAの従来のONI方式］"), fontsize=11)
        ax.text(a.index[-1], a.values[-1], f" {a.values[-1]:+.1f}", fontsize=9, va="bottom")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(alpha=0.25)
    fig.suptitle("エルニーニョ監視: 海面水温偏差の推移（観測・このサイトがNOAAのデータから計算した図）", fontsize=13, y=0.985)
    fig.subplots_adjust(top=0.93, bottom=0.17, hspace=0.18)
    _foot(fig, ["【気象庁の図ではありません】" + NOTE_OBS, "破線は ±0.5℃（エルニーニョ／ラニーニャの目安）。気象庁は NINO.3 の5か月移動平均が基準値より+0.5℃以上の状態が6か月続くとエルニーニョ現象と判断する。",
                "NOAA ERSSTv5: Huang et al. (2017) J. Climate。気象庁・NOAAの推奨を示すものではない。"])
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_forecast(res, an, year, month, path):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.2), gridspec_kw=dict(height_ratios=[1.5, 1]))
    for col, k in enumerate(("nino3", "nino34")):
        r = res[k]
        ax = axes[0, col]
        a = an[k]["anom"].dropna()
        init = pd.Timestamp(year, month, 1)
        past = a[(a.index >= init - pd.DateOffset(months=11)) & (a.index <= init)]
        fx = [pd.Timestamp(int(m[:4]), int(m[5:]), 1) for m in r["months"]]
        for mem in r["members"]:
            ax.plot(fx, mem, color="#d6604d", alpha=0.07, lw=0.8)
        ax.fill_between(fx, r["p10"], r["p90"], color="#d6604d", alpha=0.22, label="10〜90%の範囲")
        ax.plot(fx, r["mean"], color="#b2182b", lw=2.4, marker="o", label=f"アンサンブル平均（{r['n']}メンバー）")
        ax.plot(past.index, past.values, color="black", lw=2, marker="o", ms=3, label="観測（ERSSTv5）")
        ax.axhline(THRESH, color="#b2182b", ls="--", lw=1)
        ax.axhline(-THRESH, color="#2166ac", ls="--", lw=1)
        ax.axhline(0, color="#666666", lw=0.8)
        ax.set_ylabel("偏差（℃）")
        ax.set_title(f"{BOX[k][0]} 偏差の予測" + ("　［気象庁の指標］" if k == "nino3" else "　［NOAAの従来のONI方式］"), fontsize=11)
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(alpha=0.25)
        ax.tick_params(axis="x", labelrotation=30)
        # 確率の棒
        bx = axes[1, col]
        x = np.arange(len(fx))
        la, el = r["p_la"] * 100, r["p_el"] * 100
        ne = 100 - la - el
        bx.bar(x, la, color="#4393c3", label=f"ラニーニャ側（≤ −{THRESH}℃）")
        bx.bar(x, ne, bottom=la, color="#d9d9d9", label="平常")
        bx.bar(x, el, bottom=la + ne, color="#d6604d", label=f"エルニーニョ側（≥ +{THRESH}℃）")
        for i in range(len(x)):
            if el[i] >= 8:
                bx.text(x[i], la[i] + ne[i] + el[i] / 2, f"{el[i]:.0f}%", ha="center", va="center", fontsize=8)
            if la[i] >= 8:
                bx.text(x[i], la[i] / 2, f"{la[i]:.0f}%", ha="center", va="center", fontsize=8)
        bx.set_xticks(x)
        accs = [("—" if v is None else f"{v:.2f}") for v in r["acc"]]
        bx.set_xticklabels([f"{m}\n(ACC {a})" for m, a in zip(r["months"], accs)], fontsize=8)
        bx.set_ylim(0, 100)
        bx.set_ylabel("割合（%）")
        bx.set_title("メンバーの割合（過去28年の予測技能 ACC を併記）", fontsize=10)
        bx.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, fontsize=8)
    fig.suptitle(f"エルニーニョ監視: CPS4 の予測　{year}年{month}月1日基準", fontsize=13, y=0.985)
    fig.subplots_adjust(top=0.93, bottom=0.25, hspace=0.42, wspace=0.18)
    _foot(fig, ["JMA/MRI-CPS4（Copernicus C3S 経由）の海面水温を加工して作成。偏差は CPS4 ハインドキャスト 1993–2020 のモデル気候値からの差（予報155メンバーは基準日前後のラグ）。",
                "確率は、偏差が±0.5℃を超えたメンバーの割合（補正前の生の割合）。ACC は過去28年のハインドキャスト（10メンバー）と観測（ERSSTv5）の相関で、先のリードほど低い。気象庁の公式の見通しではない。",
                "予測（モデル気候値からの偏差）と観測（ERSSTv5・基準が違う）のつなぎ目には、基準の違いによる段差が出ることがある。"]
               + cps4.COPERNICUS_NOTE.format(year=year).split("\n"))
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ------------------------------------------------------------------ JSON・参考
def _round(a, n=2):
    return [None if not np.isfinite(v) else round(float(v), n) for v in a]


def latest_jma():
    fs = sorted(glob.glob(os.path.join(REF, "jma_elnino_*.json")))
    return json.load(open(fs[-1], encoding="utf-8")) if fs else None


def write_json(an, st, fc_entry):
    path = os.path.join(WEB, "enso.json")
    old = {}
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
        except ValueError:
            old = {}
    fcs = [f for f in old.get("forecasts", []) if not fc_entry or f["init"] != fc_entry["init"]]
    if fc_entry:
        fcs.append(fc_entry)
    fcs = sorted(fcs, key=lambda f: f["init"], reverse=True)[:12]
    obs = {}
    for k in ("nino3", "nino34", "roni"):
        a = an[k]["anom"].dropna().iloc[-36:]
        ma = an[k]["ma"].reindex(a.index)
        obs[k] = dict(name=BOX[k][0] if k in BOX else "RONI", base=an[k]["base"], ma_n=an[k]["ma_n"], months=[month_label(t.year, t.month) for t in a.index],
                      anom=_round(a.values), ma=_round(ma.values))
    data = dict(generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), state=st, obs=obs, obs_image="enso_obs.png", forecasts=fcs, note=NOTE_OBS)
    jma = latest_jma()
    if jma:
        data["jma"] = jma                                         # ローカルのみ（build_site.py が公開版から除く）
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=dt.date.today().year)
    ap.add_argument("--month", type=int, default=dt.date.today().month)
    ap.add_argument("--obs-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    obs = load_obs()
    an = obs_anomalies(obs)
    st = state_text(an)
    print(st["text"], flush=True)
    plot_obs(an, os.path.join(OUT, "enso_obs.png"))
    fc_entry = None
    if not a.obs_only:
        pf = os.path.join(cps4.C3S, f"jma_s4_sea_surface_temperature_monthly_mean_{a.year}-{a.month:02d}_L1-6.grib")
        if os.path.exists(pf):
            res = cps4_forecast(a.year, a.month, obs, an)
            init = f"{a.year}{a.month:02d}01"
            fig = f"enso_cps4_{init}.png"
            plot_forecast(res, an, a.year, a.month, os.path.join(OUT, fig))
            fc_entry = dict(init=init, label=f"{a.year}年{a.month}月1日基準（CPS4）", image=fig, n_members=res["nino3"]["n"])
            for k, r in res.items():
                fc_entry[k] = dict(months=r["months"], mean=_round(r["mean"]), p10=_round(r["p10"]), p90=_round(r["p90"]),
                                   p_el=_round(r["p_el"] * 100, 0), p_la=_round(r["p_la"] * 100, 0), acc=_round([np.nan if v is None else v for v in r["acc"]]))
            print(f"予測の図: {fig}（NINO.3 平均偏差 {[round(float(x), 1) for x in res['nino3']['mean']]}）", flush=True)
        else:
            print(f"CPS4 の{a.year}年{a.month}月の予報ファイルがない: 観測の図だけ作る")
    print("書き出し:", os.path.relpath(write_json(an, st, fc_entry), ROOT))


if __name__ == "__main__":
    main()
