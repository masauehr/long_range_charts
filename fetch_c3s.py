"""Copernicus C3S（CDS）の季節予報から、JMA の予報とハインドキャストの月平均を取得する（GRIB）。

- 認証: ~/.cdsapirc（ユーザーが作成。このコードはキーを読み書きしない。cdsapi が読む）。cdsapirc.sample 参照。
- データセットごとの利用規約への同意が必要（CDS の画面で手動）。
- JMA は system 4（CPS4・2026-01〜現行）。ハインドキャストは 1993–2020、予報は 2026 年（月は 2〜11）。system 3（CPS3）は
  1993–2017（ハインドキャスト）＋2018–2025（予報の一部）・2026は01月のみ（2026-11-14 時点の制約表）。
- 出力: data/c3s/jma_s{system}_{変数}_{product_type}_{年}-{月}.grib（git除外）

使い方:
    python fetch_c3s.py --bulk --year 2026 --month 11        # 4変数×(予報+ハインドキャスト1993-2020)×リード1〜6
    python fetch_c3s.py --var 2m_temperature --product monthly_mean --year 2026 --month 11 --leads 1 2 3
"""
import argparse
import os
import sys
import time

import cdsapi

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "c3s")
DATASETS = {
    "2m_temperature": "seasonal-monthly-single-levels",
    "total_precipitation": "seasonal-monthly-single-levels",
    "sea_surface_temperature": "seasonal-monthly-single-levels",
    "mean_sea_level_pressure": "seasonal-monthly-single-levels",
    "geopotential": "seasonal-monthly-pressure-levels",
}


def retrieve(var, product, years, month, leads, system="4", centre="jma", pressure=None, path=None):
    """1リクエスト分を取得して GRIB を保存し、パスを返す。"""
    ds = DATASETS[var]
    req = {
        "originating_centre": centre,
        "system": system,
        "variable": [var],
        "product_type": [product],
        "year": [str(y) for y in years],
        "month": [f"{int(month):02d}"],
        "leadtime_month": [str(k) for k in leads],
        "data_format": "grib",
    }
    if ds.endswith("pressure-levels"):
        req["pressure_level"] = [str(pressure or 500)]
    os.makedirs(OUT, exist_ok=True)
    tag = f"{years[0]}" if len(years) == 1 else f"{years[0]}-{years[-1]}"
    path = path or os.path.join(OUT, f"{centre}_s{system}_{var}_{product}_{tag}-{int(month):02d}_L{leads[0]}-{leads[-1]}.grib")
    if os.path.exists(path):
        return path
    cdsapi.Client().retrieve(ds, req, path)
    return path


BULK_VARS = ["2m_temperature", "total_precipitation", "sea_surface_temperature", "geopotential"]


def retrieve_retry(*args, tries=8, wait=120, **kw):
    """CDS の「キューに入れられる件数の上限」で拒否されたら、待って再試行する。それ以外のエラーはそのまま投げる。"""
    for i in range(tries):
        try:
            return retrieve(*args, **kw)
        except Exception as e:
            if "queued" not in str(e).lower() or i == tries - 1:
                raise
            print(f"CDSのキュー上限。{wait}秒待って再試行（{i + 1}/{tries}）", flush=True)
            time.sleep(wait)


def bulk(year, month, leads, hind_years, workers=2, hind_only=False):
    """予報(year年month月)と、ハインドキャスト(hind_years)の月平均を、4変数まとめて並列で取得する。

    hind_only=True ならハインドキャストだけ（まだ予報が出ていない月の校正用）。
    """
    from concurrent.futures import ThreadPoolExecutor
    jobs = ([] if hind_only else [(v, [year]) for v in BULK_VARS]) + [(v, hind_years) for v in BULK_VARS]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(retrieve_retry, v, "monthly_mean", ys, month, leads): (v, ys[0], ys[-1]) for v, ys in jobs}
        failed = 0
        for f, k in futs.items():
            try:
                print("保存:", f.result(), flush=True)
            except Exception as e:                                # 1件の失敗で止めず、最後に数える
                failed += 1
                print("失敗:", k, " ".join(str(e).split())[:400], flush=True)
    return failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulk", action="store_true", help="4変数×(予報+ハインドキャスト)をまとめて取得")
    ap.add_argument("--hind-years", default="1993-2020")
    ap.add_argument("--workers", type=int, default=2, help="CDS への同時リクエスト数（上限に注意。既定2）")
    ap.add_argument("--hind-only", action="store_true", help="ハインドキャストだけ取得（予報が未公開の月の校正用）")
    ap.add_argument("--var", default="2m_temperature", choices=list(DATASETS))
    ap.add_argument("--product", default="monthly_mean",
                    help="monthly_mean=メンバー別, ensemble_mean=アンサンブル平均, hindcast_climate_mean=モデル気候値 など")
    ap.add_argument("--year", nargs="+", type=int, default=[2026])
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--leads", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--system", default="4")
    a = ap.parse_args()
    if a.bulk:
        h0, _, h1 = a.hind_years.partition("-")
        n = bulk(a.year[0], a.month, [1, 2, 3, 4, 5, 6], list(range(int(h0), int(h1) + 1)), workers=a.workers, hind_only=a.hind_only)
        if n:
            print(f"取得に失敗: {n}件", file=sys.stderr)
            sys.exit(1)
        return
    print("保存:", retrieve(a.var, a.product, a.year, a.month, a.leads, system=a.system))


if __name__ == "__main__":
    main()
