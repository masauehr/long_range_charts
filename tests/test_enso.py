"""エルニーニョ監視（enso.py）と公開版の気象庁情報の除外のテスト。"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_site  # noqa: E402
import enso  # noqa: E402


def test_領域平均は欠測を除きcos緯度で重み付ける():
    lat = np.array([10.0, 0.0, -10.0])
    lon = np.array([200.0, 220.0, 240.0])
    a = np.full((3, 3), 1.0)
    a[1, 1] = 3.0
    a[0, 0] = np.nan
    box = ("t", -5, 5, 210, 230)                       # 緯度0の行・経度220の列だけ
    assert abs(enso.region_mean(a, lat, lon, box) - 3.0) < 1e-9
    assert np.isnan(enso.region_mean(np.full((3, 3), np.nan), lat, lon, box))


def _series(vals_by_year):
    idx = pd.date_range(f"{min(vals_by_year)}-01-01", periods=12 * len(vals_by_year), freq="MS")
    v = np.concatenate([np.full(12, vals_by_year[y]) for y in sorted(vals_by_year)])
    return pd.Series(v, index=idx)


def test_偏差の基準は気象庁方式と米国方式で違う():
    years = {y: 26.0 for y in range(1980, 2026)}
    years[2026] = 28.0
    s = _series(years)
    a = enso.sliding30_anomaly(s)
    assert abs(a[pd.Timestamp("2026-06-01")] - 2.0) < 1e-9          # 過去30年は26℃ → +2℃
    assert abs(a[pd.Timestamp("2015-06-01")] - 0.0) < 1e-9
    b = enso.fixed_anomaly(s)
    assert abs(b[pd.Timestamp("2026-06-01")] - 2.0) < 1e-9          # 1991〜2020年平均は26℃


def test_状態の目安():
    idx = pd.date_range("2026-01-01", periods=10, freq="MS")
    an = {"nino3": {"anom": pd.Series([0, 0, 0, 0, 0, 1.0, 1.5, 2.0, 2.5, 3.0], index=idx)}}
    st = enso.state_text(an)
    assert "エルニーニョ側" in st["kind"] and st["last_month"] == "2026-10" and st["trailing5"] == 2.0
    an["nino3"]["anom"] = pd.Series([0.0] * 10, index=idx)
    assert "平常" in enso.state_text(an)["kind"]


def test_公開版のenso_jsonには気象庁の見通しを入れない(tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (out / "enso_obs.png").write_bytes(b"x")
    (web / "enso.json").write_text(json.dumps({"obs_image": "enso_obs.png", "forecasts": [], "jma": {"status": "非公開"}}), encoding="utf-8")
    monkeypatch.setattr(build_site, "ROOT", str(tmp_path))
    site = tmp_path / "site"
    (site / "output").mkdir(parents=True)
    build_site.write_public_enso(str(site), str(out))
    d = json.load(open(site / "enso.json", encoding="utf-8"))
    assert "jma" not in d and d["imgdir"] == "output/"
    assert (site / "output" / "enso_obs.png").exists()
