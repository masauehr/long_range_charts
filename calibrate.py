"""季節ごとの校正（縮小係数）を作る。月ごとに、観測との照合をやり直して calibration.json にスロットを足す。

CFS（--cfs）: 各月の「基準の初期日」（既定は15日・年は 2026 で固定）について、過去7年の同時期のアナログ（月平均±15日・日別±7日）を取得し、
  verify.py（2m気温）と verify_cfs_vars.py（降水・Z500・水温）で校正する。1か月あたり取得約0.6GB・約2時間。
CPS4（--cps4）: 各開始月のハインドキャスト（1993–2020）だけを取得し（予報は不要）、verify_cps4.py で校正する。
  1か月あたり取得約1GB・十数分＋照合。
使い方:
  python calibrate.py --months 12 1                 # 12月と1月を CFS・CPS4 の両方で
  python calibrate.py --months 12 --only cps4       # CPS4 だけ
  python calibrate.py --months 12 1 --dry-run       # 手順だけ表示
基準の初期日は各月の中旬（15日）に置く。縮小係数は前後15日以内の初期日に使われるので、1年が切れ目なく覆える。
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

import pipeline

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
REF_YEAR = 2026


def cfs_key(month, day=15):
    return f"{REF_YEAR}{month:02d}{day:02d}"


def steps_for(month, only=None, day=15):
    steps = []
    if only in (None, "cfs"):
        t = cfs_key(month, day)
        steps += [
            (f"CFS {month}月: 月平均アナログの取得", [PY, "-W", "ignore", "fetch_cfs.py", "--target", t]),
            (f"CFS {month}月: 日別アナログの取得", [PY, "-W", "ignore", "fetch_daily.py", "--target", t, "--window", "7", "--workers", "16"]),
            (f"CFS {month}月: 2m気温の照合", [PY, "-W", "ignore", "verify.py", "--target", t, "--write"]),
            (f"CFS {month}月: 降水・Z500・水温の照合", [PY, "-W", "ignore", "verify_cfs_vars.py", "--target", t, "--write"]),
        ]
    if only in (None, "cps4"):
        steps += [
            (f"CPS4 {month}月開始: ハインドキャストの取得", [PY, "-W", "ignore", "fetch_c3s.py", "--bulk", "--hind-only", "--month", str(month)]),
            (f"CPS4 {month}月開始: 照合", [PY, "-W", "ignore", "verify_cps4.py", "--month", str(month), "--write"]),
        ]
    return steps


FETCH_TRIES = 24            # 取得の手順は、通信断に備えて最大24回（待ち10分なら約4時間）まで再試行する
STALL_SEC = 600             # CFSの取得はログが10分増えなければ固まったとみなして打ち切り、再試行する
OTHER_TRIES = 2             # 照合など、通信以外の失敗は2回まで


def run_with_retry(steps, log_path, dry=False, wait=600, until=None):
    """手順を順に実行し、失敗したら待って同じ手順をやり直す（取得は取得済みをスキップするので続きから再開できる）。

    until（epoch秒）を過ぎたら新しい手順を始めない。実行中の取得は打ち切る（保存は書き終えてから置き換えるので壊れない）。
    照合は打ち切らず、終わるまで待つ。戻り値: (成功, 記録, 期限で中断したか)。
    """
    rec = []
    for name, cmd in steps:
        tries = FETCH_TRIES if "取得" in name else OTHER_TRIES
        fetch = "取得" in name
        for i in range(tries):
            if until and time.time() >= until:
                return False, rec, True
            stall = STALL_SEC if (name.startswith("CFS") and fetch) else None     # CFSの取得だけ見張る（CDSは待ち行列で静かな時間が長い）
            ok, r = pipeline.run_steps([(name, cmd)], log_path, dry, stall_sec=stall, deadline=until if fetch else None)
            rec += r
            if ok or dry:
                break
            if "終了コード%d" % pipeline.DEADLINE_CODE in r[-1]["結果"]:
                return False, rec, True
            if i < tries - 1:
                if until and time.time() + wait >= until:
                    return False, rec, True
                print(f"  → {wait}秒待って再試行（{i + 1}/{tries - 1}）", flush=True)
                time.sleep(wait)
        if not ok and not dry:
            return False, rec, False
    return True, rec, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", type=int, required=True)
    ap.add_argument("--only", choices=["cfs", "cps4"])
    ap.add_argument("--day", type=int, default=15, help="CFS の基準日（既定15）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--until", help="この時刻（HH:MM）で中断する。取得は打ち切り、新しい手順は始めない（続きから再開できる）")
    ap.add_argument("--retry-wait", type=int, default=600, help="手順が失敗したとき再試行するまでの待ち秒（既定600）。取得は最大%d回" % FETCH_TRIES)
    a = ap.parse_args()
    steps = [s for m in a.months for s in steps_for(m, a.only, a.day)]
    tag = f"{dt.datetime.now():%Y%m%d_%H%M}_{a.only or 'all'}"
    until = None
    if a.until:                                             # "17:10" のような時刻（今日。過ぎていたら明日）
        h, m = (int(x) for x in a.until.split(":"))
        t = dt.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
        until = (t if t > dt.datetime.now() else t + dt.timedelta(days=1)).timestamp()
        print(f"期限 {dt.datetime.fromtimestamp(until):%m/%d %H:%M}（この時刻で取得を打ち切り、新しい手順を始めない）", flush=True)
    ok, rec, stopped = run_with_retry(steps, os.path.join(ROOT, "logs", f"calibrate_{tag}.log"), a.dry_run, a.retry_wait, until)
    if stopped:
        print("期限のため中断。同じコマンドで続きから再開できる。", flush=True)
    if not a.dry_run:
        with open(os.path.join(ROOT, "logs", f"last_calibrate_{a.only or 'all'}.json"), "w", encoding="utf-8") as f:
            json.dump({"月": a.months, "成功": ok, "期限で中断": stopped, "手順": rec, "終了": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f,
                      ensure_ascii=False, indent=1)
    sys.exit(0 if (ok or stopped) else 1)


if __name__ == "__main__":
    main()
