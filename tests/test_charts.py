"""charts.py の単体テスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import charts  # noqa: E402


def test_期間ラベルは30日ブロックの日付になる():
    assert charts.period_label("20261112", [0]) == "初期日から1〜30日（11/12〜12/11）の平均"
    assert charts.period_label("20261112", [1, 2, 3]) == "初期日から31〜120日（12/12〜3/11）の平均"


def test_カラーマップの区間数が合う():
    for v in charts.VARS.values():
        cm, nm = charts._anom_cmap(v["lv"], v["cmap"])
        assert cm.N == len(v["lv"]) + 1
