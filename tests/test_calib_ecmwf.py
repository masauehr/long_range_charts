"""ECMWF の校正（calib.py の ecmwf 枠・charts の係数の選択）のテスト。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calib  # noqa: E402
import charts  # noqa: E402


def test_ecmwfの校正は開始月で選ぶ(tmp_path):
    p = str(tmp_path / "cal.json")
    calib.update_ecmwf(11, meta={"方法": "t"}, alpha_var={"t2m": {"L1": {"asia": 0.8, "global": 0.7}}}, path=p)
    cal = calib.load(p)
    assert calib.ecmwf_slot(cal, 11)[0] == "11" and calib.ecmwf_slot(cal, 12) == (None, None)
    assert cal["ecmwf"]["11"]["alpha_var"]["t2m"]["L1"]["asia"] == 0.8
    assert calib.cps4_slot(cal, 11) == (None, None)            # CPS4 の枠には入らない


def test_ecmwfの係数はcfsの校正を使わない(monkeypatch):
    cal = {"version": 2, "cfs": {"20261112": {"alpha": {"M1": {"asia": 0.9, "global": 0.9}}, "alpha_var": {}}},
           "cps4": {}, "ecmwf": {}}
    monkeypatch.setattr(charts.calib, "load", lambda path=None: cal)
    assert charts.load_alpha("M1", "asia", "t2m", "20261101", "cfs") == 0.9
    assert charts.load_alpha("L1", "asia", "t2m", "20261101", "ecmwf") is None      # ECMWF の校正が無ければ未補正
    cal["ecmwf"]["11"] = {"alpha_var": {"t2m": {"L1": {"asia": 0.55, "global": 0.5}}}}
    assert charts.load_alpha("L1", "asia", "t2m", "20261101", "ecmwf") == 0.55
    assert charts.load_alpha("L1", "asia", "t2m", "20261201", "ecmwf") is None      # 別の開始月には適用しない
