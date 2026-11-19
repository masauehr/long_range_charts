"""data/ の古い取得ファイルの整理（既定は確認だけ。--apply を付けたときだけ削除する）。

削除する対象（図・中間ファイルの作成後は使わず、再取得もできるもの）:
  A. data/cfs_daily_lag/{対象日}/ … ラグアンサンブル用の取得（1回約110MB）。対象日が --lag-days（既定14）日より古いもの。
  B. data/c3s/ の予報側 GRIB（2026年以降の「予報」。JMA のハインドキャストは対象外）。更新から --grib-days（既定45）日より古いもの。
  C. data/c3s/ の ECMWF のハインドキャスト GRIB（ecmwf_s51_*_1993-2016-*）。更新から --hind-days（既定45）日より古いもの（再取得できる）。
削除しないもの:
  - 2019–2025 年の初期日データ（cfs_daily・cfs_monthly・cfs_dyn・cfs_dyn_daily）… 気候値・校正の元。
  - 2026 年以降の初期日ごとの npz（1回約30MB）… 気候値へ2026年分を足すときに使う（小さいので残す）。
  - JMA のハインドキャスト GRIB（1993–2020）・ref_psl・data/*.npz（図の元の中間ファイル）。
安全: data/ の外は触らない。削除は os.remove / os.rmdir のみ（再帰削除はしない）。
使い方:
  python cleanup.py                 # 対象と容量を表示するだけ
  python cleanup.py --apply         # 実際に削除する
"""
import argparse
import datetime as dt
import os
import re
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.realpath(os.path.join(ROOT, "data"))
LAG = os.path.join(DATA, "cfs_daily_lag")
C3S = os.path.join(DATA, "c3s")
# 予報側 GRIB の名前: ..._monthly_mean_2026-11_L1-6.grib ／ ..._monthly_mean_2026_p850-200-11_L1-6.grib
# （ハインドキャストは 1993-2020 を含むので、この形には一致しない）
RE_HIND_ECMWF = re.compile(r"^ecmwf_s51_.*_monthly_mean_1993-2016(_p850-200)?-\d{2}_L1-6\.grib$")        # ECMWF のハインドキャスト（再取得は約45分）
RE_FC = [re.compile(r"monthly_mean_(\d{4})-\d{2}_L1-6\.grib$"), re.compile(r"monthly_mean_(\d{4})_p850-200-\d+_L1-6\.grib$")]


def inside_data(path):
    """data/ の中にあるか（シンボリックリンクで外へ出ていないか）を確かめる。"""
    return os.path.realpath(path).startswith(DATA + os.sep)


def lag_targets(today, days):
    """削除するラグ取得のフォルダ [(パス, ファイル一覧, バイト数)]。"""
    out = []
    if not os.path.isdir(LAG):
        return out
    for name in sorted(os.listdir(LAG)):
        p = os.path.join(LAG, name)
        if not (os.path.isdir(p) and re.fullmatch(r"\d{8}", name)):
            continue
        try:
            d = dt.datetime.strptime(name, "%Y%m%d").date()
        except ValueError:
            continue
        if (today - d).days <= days:
            continue
        files = [os.path.join(p, f) for f in os.listdir(p)]
        if any(not (f.endswith(".npz") and os.path.isfile(f)) for f in files):   # 想定外のものがあれば触らない
            print(f"  スキップ（想定外のファイルあり）: {p}")
            continue
        out.append((p, files, sum(os.path.getsize(f) for f in files)))
    return out


def grib_targets(now, days, hind_days=None):
    """削除する予報側 GRIB と ECMWF のハインドキャスト GRIB [(パス, バイト数)]。"""
    hind_days = days if hind_days is None else hind_days
    out = []
    if not os.path.isdir(C3S):
        return out
    for name in sorted(os.listdir(C3S)):
        hind = bool(RE_HIND_ECMWF.match(name))
        if not hind and not any(r.search(name) for r in RE_FC):
            continue
        p = os.path.join(C3S, name)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            continue
        if (now - os.path.getmtime(p)) / 86400 <= (hind_days if hind else days):
            continue
        out.append((p, os.path.getsize(p)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="実際に削除する（省略時は表示だけ）")
    ap.add_argument("--lag-days", type=int, default=14, help="ラグ取得を残す日数（既定14）")
    ap.add_argument("--grib-days", type=int, default=45, help="予報側GRIBを残す日数（既定45）")
    ap.add_argument("--hind-days", type=int, default=45, help="ECMWFのハインドキャストGRIBを残す日数（既定45。JMAのハインドキャストは対象外）")
    a = ap.parse_args()

    lags = lag_targets(dt.date.today(), a.lag_days)
    gribs = grib_targets(time.time(), a.grib_days, a.hind_days)
    total = sum(b for _, _, b in lags) + sum(b for _, b in gribs)
    mode = "削除" if a.apply else "確認のみ（削除しない）"
    print(f"[整理 {mode}] ラグ取得 {len(lags)} 件・予報GRIB {len(gribs)} 件・合計 {total / 1e9:.2f}GB")
    for p, files, b in lags:
        print(f"  ラグ  {os.path.relpath(p, ROOT)}（{len(files)}ファイル・{b / 1e6:.0f}MB）")
    for p, b in gribs:
        print(f"  GRIB  {os.path.relpath(p, ROOT)}（{b / 1e6:.0f}MB）")
    if not a.apply:
        return
    done = 0
    for p, files, _ in lags:
        if not inside_data(p):
            continue
        for f in files:
            os.remove(f)
        os.rmdir(p)
        done += 1
    for p, _ in gribs:
        if inside_data(p):
            os.remove(p)
            done += 1
    print(f"削除しました: {done} 件・{total / 1e9:.2f}GB")


if __name__ == "__main__":
    main()
