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
