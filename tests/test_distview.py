"""distview.py（地点の分布図のデータ）のテスト。"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import distview  # noqa: E402


def _grid():
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    return lat, lon


def test_ヒストグラムは件数を保ち予報メンバーを含む範囲になる(tmp_path):
    lat, lon = _grid()
    rng = np.random.default_rng(0)
    samples = rng.normal(10, 2, size=(200, len(lat), len(lon)))
    members = np.full((4, len(lat), len(lon)), 20.0)                  # 気候値の分布より大きく外れた予報
    c = distview.Collector()
    c.add("t2m", "W1", samples, members, lat, lon)
    path = c.write("cfs_week", "20261116", str(tmp_path))
    d = json.load(open(path, encoding="utf-8"))
    nb, cells = d["nb"], len(d["lat"]) * len(d["lon"])
    r = d["vars"]["t2m"]["W1"]
    assert len(r["cc"]) == cells * nb and len(r["fc"]) == cells * nb and len(r["lo"]) == cells
    assert sum(r["cc"][:nb]) == 200 and sum(r["fc"][:nb]) == 4         # どの地点でも件数が保たれる
    assert all(h >= 20.0 for h in r["hi"])                            # 範囲が予報メンバーを含む
    assert r["n"] == 200 and r["m"] == 4
    assert d["lat"][0] == 60.0 and min(d["lon"]) >= 95 and max(d["lon"]) <= 175


def test_CPS4は1_25度を間引く(tmp_path):
    lat = np.arange(90, -90.1, -1.25)
    lon = np.arange(0, 360, 1.25)
    s = np.random.default_rng(1).normal(size=(30, len(lat), len(lon)))
    m = np.random.default_rng(2).normal(size=(10, len(lat), len(lon)))
    c = distview.Collector()
    c.add("t2m", "L1", s, m, lat, lon)
    assert np.allclose(np.diff(c.grid[0]), -2.5) and np.allclose(np.diff(c.grid[1]), 2.5)
