"""climview.py（気候値の図・地点の数値）のテスト。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import charts  # noqa: E402
import climview  # noqa: E402


def test_地点の数値は東アジアの格子で縮小係数を適用する(monkeypatch):
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    shape = (len(lat), len(lon))
    d = dict(mean=np.full(shape, 10.0), t33=np.full(shape, 9.0), t67=np.full(shape, 11.0), anom=np.full(shape, 2.0),
             pu=np.full(shape, 1.0), pl=np.full(shape, 0.0))
    monkeypatch.setattr(charts, "load_alpha", lambda *a, **k: 0.5)
    out = climview.build_points("cfs_week", "20261116", lat, lon, {"W1": "予報1〜7日目"}, {"t2m": {"W1": d}})
    assert out["lat"][0] == 60.0 and out["lat"][-1] == 10.0          # 北緯8〜62°の範囲にある 2.5° 格子
    assert min(out["lon"]) >= 95 and max(out["lon"]) <= 175
    r = out["vars"]["t2m"]["periods"]["W1"]
    n = len(out["lat"]) * len(out["lon"])
    assert len(r["mean"]) == n and r["mean"][0] == 10.0 and r["fc"][0] == 12.0 and r["anom"][0] == 2.0
    assert r["pu"][0] == round((1 / 3 + 0.5 * (1 - 1 / 3)) * 100) and r["pl"][0] == round((1 / 3 + 0.5 * (0 - 1 / 3)) * 100)
    assert r["alpha"] == 0.5


def test_CPS4は1_25度を2_5度に間引く(monkeypatch):
    lat = np.arange(90, -90.1, -1.25)
    lon = np.arange(0, 360, 1.25)
    shape = (len(lat), len(lon))
    one = np.ones(shape)
    d = dict(mean=one, t33=one, t67=one, anom=one * 0, pu=one * 0.4, pl=one * 0.2)
    monkeypatch.setattr(charts, "load_alpha", lambda *a, **k: None)
    out = climview.build_points("cps4", "20261101", lat, lon, {"L1": "11月"}, {"t2m": {"L1": d}})
    assert np.allclose(np.diff(out["lat"]), -2.5) and np.allclose(np.diff(out["lon"]), 2.5)
    assert out["vars"]["t2m"]["periods"]["L1"]["alpha"] is None and out["vars"]["t2m"]["periods"]["L1"]["pu"][0] == 40
