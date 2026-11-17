"""telecon.py（テレコネクション指数）のテスト。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import telecon  # noqa: E402


def test_指数の重みの合計は0():
    for k, d in telecon.INDICES.items():
        assert abs(sum(p[2] for p in d["pts"])) < 1e-12, k


def test_点の値は最寄りの格子で西経は東経に直す():
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    z = np.tile(lon, (len(lat), 1)) + 1000 * np.tile(lat[:, None], (1, len(lon)))       # 値から格子の位置が分かる
    v = telecon.point_values(z, lat, lon, [(20, -160, 1.0)])
    assert v[0] == 200.0 + 1000 * 20.0


def test_指数は気候値の平均を引いた偏差の組み合わせ():
    rng = np.random.default_rng(0)
    clim_s = rng.normal(5500, 40, size=(300, 2))                                   # WP の2点
    pts = telecon.INDICES["WP"]["pts"]
    members = np.array([[5600.0, 5400.0], [5700.0, 5300.0]])                        # 点1が高く点2が低い → 正
    st = telecon.index_stats("WP", clim_s, members, np.zeros(300))
    assert st["fc"] > 100 and st["z"] > 0 and st["pct"] > 90 and len(st["members"]) == 2
