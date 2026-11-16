"""力学診断（fetch_dyn.py・dyn.py・distview の統合）のテスト。"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import distview  # noqa: E402
import dyn  # noqa: E402
import fetch_dyn  # noqa: E402


def test_uとvが同じ位置に並ぶ索引からまとまりのバイト範囲を取る():
    idx = ["10:100:d=x:HGT:200 mb:", "11.1:200:d=x:UGRD:200 mb:", "11.2:200:d=x:VGRD:200 mb:", "12:300:d=x:ABSV:200 mb:"]
    offs = [int(line.split(":")[1]) for line in idx]
    assert fetch_dyn._range_for(idx, offs, r":UGRD:200 mb:") == "bytes=200-299"      # u・v 2フィールドをまとめて
    assert fetch_dyn._range_for(idx, offs, r":HGT:200 mb:") == "bytes=100-199"
    assert fetch_dyn._range_for(idx, offs, r":TMP:") is None
    assert fetch_dyn._range_for(idx, offs, r":ABSV:200 mb:") == "bytes=300-"        # 最後の行は終端まで


def test_対象と同じ月の初期日のサンプルだけを読む(tmp_path):
    lat, lon = np.arange(90, -90.1, -2.5), np.arange(0, 360, 2.5)
    arr = np.zeros((4, 4, 4, len(lat), len(lon)), "float32")
    for d in ("20191110", "20191130", "20191201"):                    # 12/1 は対象（11月）と別の月
        np.savez_compressed(tmp_path / f"{d}.npz", arr=arr, lat=lat, lon=lon, vars=fetch_dyn.NAMES)
    x, off, yr, la, lo = dyn.load_samples("20261116", [2019], 15, d_dir=str(tmp_path))
    assert x.shape[0] == 8 and set(off) == {-6.0, 14.0} and set(yr) == {2019}       # 2日×4メンバー・12/1 は除かれる


def test_分布図のデータは別の作図が足した変数を消さずに統合する(tmp_path):
    lat, lon = np.arange(90, -90.1, -2.5), np.arange(0, 360, 2.5)
    s = np.random.default_rng(0).normal(size=(20, len(lat), len(lon)))
    m = np.random.default_rng(1).normal(size=(4, len(lat), len(lon)))
    c1 = distview.Collector()
    c1.add("t2m", "M1", s, m, lat, lon)
    c1.write("cfs_month", "20261116", str(tmp_path))
    c2 = distview.Collector()
    c2.add("psi200", "M1", s, m, lat, lon)
    p = c2.write("cfs_month", "20261116", str(tmp_path))
    d = json.load(open(p, encoding="utf-8"))
    assert set(d["vars"]) == {"t2m", "psi200"}
    c3 = distview.Collector()                                          # 通常の作図をやり直しても力学診断は残る
    c3.add("t2m", "M1", s, m, lat, lon)
    p = c3.write("cfs_month", "20261116", str(tmp_path))
    assert set(json.load(open(p, encoding="utf-8"))["vars"]) == {"t2m", "psi200"}
