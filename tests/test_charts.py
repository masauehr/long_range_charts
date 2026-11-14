"""charts.py の単体テスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import charts  # noqa: E402


def test_期間ラベルは暦月になる():
    assert charts.period_label("20261112", [0]) == "11月（11/12〜11/30）の平均"
    assert charts.period_label("20261112", [1]) == "12月の月平均"
    assert charts.period_label("20261112", [1, 2, 3]) == "12〜2月の3か月平均"


def test_カラーマップの区間数が合う():
    for v in charts.VARS.values():
        cm, nm = charts._anom_cmap(v["lv"], v["cmap"])
        assert cm.N == len(v["lv"]) + 1


def test_週平均の窓ラベル():
    import weekly
    assert weekly.span_label("20261112", (1, 7)) == "予報1〜7日目（11/12〜11/18）の平均"
    assert weekly.span_label("20261112", (3, 30)) == "予報3〜30日目（11/14〜12/11）の平均"


def test_週平均の窓統計の形():
    import numpy as np
    import weekly
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, (40, 30, 1, 2, 3)).astype("float32")
    off = np.tile(np.arange(-4, 4), 5).astype(float)
    z = rng.normal(0, 1, (4, 30, 1, 2, 3)).astype("float32")
    c, anom, up, lo, zp = weekly.window_stats(x, off, z, (3, 9))
    assert anom.shape == (1, 2, 3) and up.shape == (1, 2, 3) and zp.shape == (4, 1, 2, 3)
