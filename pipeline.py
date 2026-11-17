"""取得 → 作図 → 閲覧画面の一覧更新を、1コマンドで回す（Phase 5・ローカル自動化）。

CFS モード（既定）: 最新の完全な初期日（00Z）を探し、月平均・日別・ラグの取得、L2/L1の作図、manifest 更新まで。
  python pipeline.py                      # 最新の完全な初期日で実行
  python pipeline.py --target 20261113    # 初期日を指定
  python pipeline.py --dry-run            # 手順だけ表示（取得も作図もしない）
CPS4 モード（月1回）: C3S の JMA CPS4（基準日=月初）を取得して作図。
  python pipeline.py --cps4 --year 2026 --month 12
  python pipeline.py --cps4                # 年月を省略すると今月（月次の自動実行用）
  ※ 縮小係数は校正した季節（CFS=校正した基準日の前後15日・CPS4=校正した開始月）の外では適用されず、図に「未補正」と出る。

安全装置:
- 1段階が失敗したら以降は止め、logs/last_run.json に記録する（終了コードは非0）。
- 取得済みのファイルはスキップ（途中から再開できる）。
- data/ が上限（--max-gb・既定40GB）を超えていたら取得を始めない。
- 最後の手順で古い取得ファイルを整理する（cleanup.py: 14日より古いラグ取得・45日より古い予報側C3S GRIBのみ。2019–2025年のデータ・2026年以降の初期日ごとのnpz・ハインドキャストは消さない）。
- 最後の手順で公開サイトを更新する（build_site.py --publish。gh-pages へ force push。--no-publish で省略）。
"""
import argparse
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

import fetch_cfs

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
LOGS = os.path.join(ROOT, "logs")
STATUS = os.path.join(LOGS, "last_run.json")


def head_ok(url):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
        return True
    except Exception:
        return False


def is_complete(date):
    """初期日(00Z)のデータが、このパイプラインで使うぶん揃っているか。

    月平均: メンバー01は7か月分以上・メンバー02〜04は4か月分以上。日別: メンバー01〜04の tmp2m・prate・z500 の .idx がある。
    """
    try:
        f1 = fetch_cfs.list_month_files(date, 1).get("flxf", [])
        if len(f1) < 7:
            return False
        for m in (2, 3, 4):
            if len(fetch_cfs.list_month_files(date, m).get("flxf", [])) < 4:
                return False
        for m in (1, 2, 3, 4):
            for v in ("tmp2m", "prate", "z500"):
                key = f"cfs.{date}/00/time_grib_{m:02d}/{v}.{m:02d}.{date}00.daily.grb2.idx"
                if not head_ok(fetch_cfs.BASE + key):
                    return False
        return True
    except Exception:
        return False


def latest_complete_init(today=None, back=7, check=is_complete):
    """今日（UTC）から遡って、最初に完全な初期日（YYYYMMDD）を返す。見つからなければ None。"""
    t = today or dt.datetime.utcnow().date()
    for d in range(0, back + 1):
        day = (t - dt.timedelta(days=d)).strftime("%Y%m%d")
        if check(day):
            return day
    return None


def data_gb():
    total = 0
    for root, _, files in os.walk(os.path.join(ROOT, "data")):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1e9


def cfs_steps(target):
    """CFS モードの手順 [(名前, コマンド)]。"""
    return [
        ("月平均の取得", [PY, "-W", "ignore", "fetch_cfs.py", "--target", target]),
        ("日別の取得", [PY, "-W", "ignore", "fetch_daily.py", "--target", target, "--window", "7", "--workers", "16"]),
        ("ラグ用の取得", [PY, "-W", "ignore", "fetch_daily.py", "--target", target, "--lag-days", "2", "--workers", "16"]),
        ("力学診断の取得(CFS・月平均)", [PY, "-W", "ignore", "fetch_dyn.py", "--target", target]),
        ("力学診断の取得(CFS・日別)", [PY, "-W", "ignore", "fetch_dyn_daily.py", "--target", target, "--workers", "12"]),
        ("月平均の作図(L2)", [PY, "-W", "ignore", "charts.py", "--target", target]),
        ("週平均の作図(L1)", [PY, "-W", "ignore", "weekly.py", "--target", target]),
        ("週平均の作図(L1・ラグ)", [PY, "-W", "ignore", "weekly.py", "--target", target, "--lagged"]),
        ("力学診断の作図(CFS・月平均)", [PY, "-W", "ignore", "dyn.py", "--target", target]),
        ("力学診断の作図(CFS・週平均)", [PY, "-W", "ignore", "weekly_dyn.py", "--target", target]),
        ("気象庁形式の図(CFS・週平均)", [PY, "-W", "ignore", "jma_style.py", "--series", "cfs_week", "--init", target]),
        ("気象庁形式の図(CFS)", [PY, "-W", "ignore", "jma_style.py", "--series", "cfs_month", "--init", target]),
        ("テレコネクション指数(CFS)", [PY, "-W", "ignore", "telecon.py", "--series", "cfs_month", "cfs_week", "--init", target]),
        ("エルニーニョ監視(CFS予測)", [PY, "-W", "ignore", "enso.py", "--skip-cps4", "--cfs-init", target]),
        ("気候値の図・地点の数値(CFS)", [PY, "-W", "ignore", "climview.py", "--series", "cfs_week", "cfs_month", "--init", target]),
        ("一覧の更新", [PY, "-W", "ignore", "make_web.py"]),
        ("公開サイトの更新", [PY, "-W", "ignore", "build_site.py", "--keep", "6", "--publish"]),
        ("古い取得ファイルの整理", [PY, "-W", "ignore", "cleanup.py", "--apply"]),
    ]


def cps4_steps(year, month):
    return [
        ("C3S取得(予報+ハインドキャスト)", [PY, "-W", "ignore", "fetch_c3s.py", "--bulk", "--year", str(year), "--month", str(month)]),
        ("C3S取得(力学診断: 850・200hPaの風・OLR)", [PY, "-W", "ignore", "fetch_c3s.py", "--dyn", "--year", str(year), "--month", str(month)]),
        ("CPS4の作図", [PY, "-W", "ignore", "cps4.py", "--year", str(year), "--month", str(month)]),
        ("CPS4の力学診断の作図", [PY, "-W", "ignore", "cps4_dyn.py", "--year", str(year), "--month", str(month)]),
        ("気象庁形式の図(CPS4)", [PY, "-W", "ignore", "jma_style.py", "--series", "cps4", "--init", f"{year}{month:02d}01"]),
        ("テレコネクション指数(CPS4)", [PY, "-W", "ignore", "telecon.py", "--series", "cps4", "--init", f"{year}{month:02d}01"]),
        ("気候値の図・地点の数値(CPS4)", [PY, "-W", "ignore", "climview.py", "--series", "cps4", "--init", f"{year}{month:02d}01"]),
        ("エルニーニョ監視", [PY, "-W", "ignore", "enso.py", "--year", str(year), "--month", str(month)]),
        ("一覧の更新", [PY, "-W", "ignore", "make_web.py"]),
        ("公開サイトの更新", [PY, "-W", "ignore", "build_site.py", "--keep", "6", "--publish"]),
        ("古い取得ファイルの整理", [PY, "-W", "ignore", "cleanup.py", "--apply"]),
    ]


STALL_CODE = 124
DEADLINE_CODE = 125          # 期限（--until）で打ち切った


def run_one(cmd, log_path, stall_sec=None, poll=10, deadline=None):
    """1手順を実行して終了コードを返す。stall_sec 秒のあいだログが増えなければ、固まったとみなして打ち切る（終了コード124）。

    通信断で開いたままの接続に、プロセスがぶら下がって止まるのを防ぐ。stall_sec=None なら見張らない。
    deadline（epoch秒）を過ぎたら打ち切る（終了コード125）。再開できる手順（取得）にだけ使う。
    """
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.flush()
        if not stall_sec and not deadline:
            return subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT).returncode
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
        last, size = time.time(), os.path.getsize(log_path)
        while p.poll() is None:
            time.sleep(poll)
            now = os.path.getsize(log_path)
            if now != size:
                size, last = now, time.time()
            code = None
            if deadline and time.time() >= deadline:
                lf.write("\n[期限] 指定の時刻になったので打ち切る（取得済みの分は残り、続きから再開できる）\n")
                code = DEADLINE_CODE
            elif stall_sec and time.time() - last > stall_sec:
                lf.write(f"\n[見張り] {stall_sec}秒のあいだ出力が無いので打ち切る（固まったとみなす）\n")
                code = STALL_CODE
            if code:
                lf.flush()
                for sig in (signal.SIGTERM, signal.SIGKILL):          # 子プロセスもまとめて止める
                    try:
                        os.killpg(p.pid, sig)
                    except ProcessLookupError:
                        break
                    try:
                        p.wait(timeout=10)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                return code
        return p.returncode


def run_steps(steps, log_path, dry=False, stall_sec=None, poll=10, deadline=None):
    """手順を順に実行する。失敗したら止める。戻り値: (成功, 記録のリスト)。stall_sec は run_one を参照。"""
    rec = []
    for name, cmd in steps:
        t0 = time.time()
        print(f"[{name}] {' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))}", flush=True)
        if dry:
            rec.append({"手順": name, "結果": "dry-run"})
            continue
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"\n===== {name} {dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        rc = run_one(cmd, log_path, stall_sec, poll, deadline)
        sec = round(time.time() - t0)
        rec.append({"手順": name, "結果": "成功" if rc == 0 else f"失敗(終了コード{rc})", "秒": sec})
        print(f"  → {rec[-1]['結果']}（{sec}秒）", flush=True)
        if rc != 0:
            return False, rec
    return True, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", help="CFS の初期日 YYYYMMDD（省略なら最新の完全な初期日）")
    ap.add_argument("--cps4", action="store_true", help="CPS4（C3S）モード")
    ap.add_argument("--year", type=int)
    ap.add_argument("--month", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-publish", action="store_true", help="公開サイトの更新（gh-pages への push）を省く")
    ap.add_argument("--max-gb", type=float, default=40.0)
    a = ap.parse_args()
    os.makedirs(LOGS, exist_ok=True)
    now = dt.datetime.now()
    status = {"開始": now.strftime("%Y-%m-%d %H:%M:%S"), "モード": "cps4" if a.cps4 else "cfs"}
    log_path = os.path.join(LOGS, f"pipeline_{now:%Y%m%d}.log")
    try:
        if not a.dry_run and data_gb() > a.max_gb:
            raise RuntimeError(f"data/ が上限 {a.max_gb}GB を超えている（{data_gb():.1f}GB）。片付けてから実行すること。")
        if a.cps4:
            if not (a.year and a.month):                    # 省略（launchd の月次実行）なら今月
                a.year, a.month = now.year, now.month
            status["対象"] = f"{a.year}-{a.month:02d}"
            steps = cps4_steps(a.year, a.month)
        else:
            target = a.target or latest_complete_init()
            if not target:
                raise RuntimeError("完全な初期日が見つからない（AWS の更新待ちか、取得できない）。")
            status["対象"] = target
            print(f"対象の初期日: {target}", flush=True)
            steps = cfs_steps(target)
        if a.no_publish:
            steps = [st for st in steps if st[0] != "公開サイトの更新"]
        ok, rec = run_steps(steps, log_path, a.dry_run)
        status.update({"成功": ok, "手順": rec})
    except Exception as e:                                  # 想定外も記録して非0で終わる
        ok = False
        status.update({"成功": False, "エラー": str(e)})
        print("エラー:", e, file=sys.stderr)
    status["終了"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not a.dry_run:
        with open(STATUS, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
