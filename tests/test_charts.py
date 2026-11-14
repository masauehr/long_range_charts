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
