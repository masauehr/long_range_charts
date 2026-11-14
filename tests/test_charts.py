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


def test_ラグメンバーは初期日のずれの傾きで補正される():
    import numpy as np
    import weekly
    rng = np.random.default_rng(4)
    off = np.tile(np.arange(-7, 8), 6).astype(float)
    x = (0.5 * off)[:, None, None, None, None] + rng.normal(0, 0.05, (off.size, 30, 1, 2, 3))
    z = rng.normal(0, 0.05, (4, 30, 1, 2, 3)).astype("float32")
    lag_arr = np.full((30, 1, 2, 3), 0.5 * -1.0, dtype="float32")        # 初期日が1日前のメンバー（傾き0.5/日）
    c, anom, up, lo, zp = weekly.window_stats(x.astype("float32"), off, z, (3, 9), lag=([lag_arr], [-1.0]))
    assert zp.shape[0] == 5
    assert abs(float(zp[4].mean())) < 0.1          # 補正後は対象の初期日の水準（≒0）になる


def test_確率の縮小は気候値へ寄る():
    import numpy as np
    assert abs(charts.shrink(1.0, 0.5) - (1 / 3 + 0.5 * 2 / 3)) < 1e-12
    assert abs(charts.shrink(0.0, 0.0) - 1 / 3) < 1e-12
    assert np.allclose(charts.shrink(np.array([1 / 3]), 0.2), 1 / 3)
    assert charts.load_alpha("W1", "asia") is not None
    assert charts.load_alpha("W9", "asia") is None


def test_C3Sの図に出典と免責が入る():
    import cps4
    note = cps4.COPERNICUS_NOTE.format(year=2026)
    assert "Generated using Copernicus Climate Change Service information 2026" in note
    assert "Neither the European Commission nor ECMWF is responsible" in note
    assert "10.24381/cds.68dd14c3" in note


def test_欠測マスクはNaNになる():
    import numpy as np
    import cps4
    v = np.ma.masked_array([1.0, 9999.0, 3.0], mask=[False, True, False])
    out = cps4.to_float(v)
    assert np.isnan(out[1]) and out[0] == 1.0 and out[2] == 3.0


def test_CFS月平均の既定変数はclimの変数と一致する():
    import clim
    assert set(clim.VARS) <= set(charts.VARS)
    assert "sst" in charts.VARS and "sst" not in clim.VARS      # sst は CPS4（C3S）用
