"""季節別の校正（calibrate.py）の進み具合を1コマンドで表示する。読むだけで、何も変更しない。

表示: 校正済みの月（CFS・CPS4）、動いている校正プロセス、現在の手順と件数、残り時間の目安。
使い方: python calibrate_status.py
残り時間は、完了した月の所要時間（中央値）と、今の手順の件数の進み具合から出した目安。取得先の速度で大きく変わる。
"""
import datetime as dt
import glob
import os
import re
import statistics
import subprocess

import calib

ROOT = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(ROOT, "logs")
STEP = re.compile(r"^\[(CFS|CPS4) (\d+)月[^:：]*[:：]\s*([^\]]*)\]")
DONE = re.compile(r"→ (成功|失敗\S*)（(\d+)秒）")
COUNT = re.compile(r"\[(\d+)/(\d+)\]")


def fmt(sec):
    sec = int(sec)
    return f"{sec // 3600}時間{sec % 3600 // 60:02d}分" if sec >= 3600 else f"{sec // 60}分"


def calibrated():
    cal = calib.load()
    cfs = sorted({int(k[4:6]) for k in cal["cfs"]})
    cps = sorted(int(k) for k in cal["cps4"])
    return cfs, cps


def running():
    out = subprocess.run(["pgrep", "-fl", "calibrate.py"], capture_output=True, text=True).stdout
    return [l.split("calibrate.py", 1)[1].strip() for l in out.splitlines() if "calibrate.py" in l and "pgrep" not in l]


def month_seconds(run_out):
    """実行出力から、月ごとの所要秒数 {(種別,月): 秒} と、最後の（未完了の）手順を返す。"""
    per, last = {}, None
    cur = None
    with open(run_out, encoding="utf-8") as f:
        for line in f:
            m = STEP.match(line)
            if m:
                cur = (m.group(1), int(m.group(2)), m.group(3))
                last = cur
                continue
            d = DONE.search(line)
            if d and cur:
                per[cur[:2]] = per.get(cur[:2], 0) + int(d.group(2))
                if d.group(1) == "成功":
                    last = None                                 # 直前の手順は完了
    return per, last


def main():
    cfs, cps = calibrated()
    print(f"校正済み  CFS {len(cfs)}/12か月: {cfs}")
    print(f"          CPS4 {len(cps)}/12か月: {cps}")
    procs = running()
    print(f"動作中の校正プロセス: {len(procs)}件" + "".join(f"\n  - calibrate.py {p}" for p in procs))
    for kind, done in (("cfs", cfs), ("cps4", cps)):
        outs = sorted(glob.glob(os.path.join(LOGS, f"calibrate_{kind}_run*.out")), key=os.path.getmtime)
        if not outs:
            continue
        per, last = month_seconds(outs[-1])
        times = [v for (k, _), v in per.items() if k.lower() == kind.lower() and v > 60][-3:]
        med = statistics.median(times) if times else None
        print(f"\n[{kind.upper()}] 最新の実行: {os.path.basename(outs[-1])}")
        if not last:
            print("  実行中の手順なし（終了済み）")
            continue
        print(f"  いまの手順: {last[1]}月 {last[2]}")
        logs = sorted(glob.glob(os.path.join(LOGS, f"calibrate_*_{kind}.log")), key=os.path.getmtime)
        if logs:
            with open(logs[-1], encoding="utf-8", errors="replace") as f:
                counts = COUNT.findall(f.read()[-4000:])
            if counts:
                n, tot = counts[-1]
                print(f"  件数: {n}/{tot}（{int(n) * 100 // max(int(tot), 1)}%）")
            age = dt.datetime.now().timestamp() - os.path.getmtime(logs[-1])
            print(f"  ログの最終更新: {fmt(age)}前" + ("（止まっている可能性）" if age > 1800 else ""))
        if med:
            remain_m = [m for m in range(1, 13) if m not in done and m != last[1]]
            print(f"  目安: 1か月あたり約{fmt(med)}（直近の完了月の中央値）。残り{len(remain_m) + 1}か月で約{fmt(med * (len(remain_m) + 0.5))}")


if __name__ == "__main__":
    main()
