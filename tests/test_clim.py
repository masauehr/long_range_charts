"""clim.py の単体テスト（合成データ）。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clim  # noqa: E402


def test_初期日のずれの傾きを補正できる():
    rng = np.random.default_rng(0)
    off = np.tile(np.arange(-15, 16), 7).astype(float)
    x = (10 + 0.2 * off + rng.normal(0, 1, off.size)).reshape(-1, 1, 1).astype("float32")
    xa, b = clim.adjust_offset(x, off)
    assert abs(b[0, 0] - 0.2) < 0.02
    assert abs(np.polyfit(off, xa[:, 0, 0], 1)[0]) < 1e-3


def test_NaNを含んでも傾きと三分位が出る():
    rng = np.random.default_rng(1)
    off = np.tile(np.arange(-5, 6), 20).astype(float)
    x = rng.normal(0, 1, (off.size, 2)).astype("float32")
    x[::3, 1] = np.nan
    c = clim.make_clim(x, off)
    assert np.isfinite(c["t33"]).all() and (c["t33"] < c["t67"]).all()


def test_三分位確率は母集団で約三分の一になる():
    rng = np.random.default_rng(2)
    off = np.zeros(900)
    x = rng.normal(0, 1, (900, 1)).astype("float32")
    c = clim.make_clim(x, off)
    up, lo, n = clim.tercile_prob(x, c)
    assert abs(up[0] - 1 / 3) < 0.01 and abs(lo[0] - 1 / 3) < 0.01 and n[0] == 900


def test_トレンド補正で基準年の水準へ揃う():
    lat = np.array([0.0, 30.0])
    yr = np.repeat(np.arange(2019, 2026), 3)
    # 全球一様に 2/年 で増える合成データ [サンプル, リード1, 変数1, 緯2, 経2]
    x = (10 + 2.0 * (yr - 2019))[:, None, None, None, None] * np.ones((yr.size, 1, 1, 2, 2))
    xa, b = clim.trend_adjust(x.astype("float32"), yr, 2026, lat)
    assert abs(b[0, 0] - 2.0) < 1e-4
    assert np.allclose(xa, 10 + 2.0 * 7, atol=1e-3)


def test_空間相関の基本性質():
    import verify
    w = np.ones((3, 4))
    a = np.arange(12, dtype=float).reshape(3, 4)
    assert abs(verify.wcorr(a, a * 2 + 5, w) - 1.0) < 1e-9
    assert abs(verify.wcorr(a, -a, w) + 1.0) < 1e-9
