"""cleanup.py の対象判定のテスト（削除はしない・一時フォルダで確認する）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cleanup  # noqa: E402


def _touch(path, age_days):
    with open(path, "wb") as f:
        f.write(b"x" * 10)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


def test_古い予報GRIBとECMWFハインドキャストだけが対象(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "C3S", str(tmp_path))
    old = 100
    names = {
        "jma_s4_2m_temperature_monthly_mean_2026-11_L1-6.grib": True,                       # JMA の予報（古い）→ 対象
        "jma_s4_u_component_of_wind_monthly_mean_2026_p850-200-11_L1-6.grib": True,         # 風の予報 → 対象
        "jma_s4_2m_temperature_monthly_mean_1993-2020-11_L1-6.grib": False,                 # JMA のハインドキャスト → 残す
        "ecmwf_s51_2m_temperature_monthly_mean_2026-11_L1-6.grib": True,                    # ECMWF の予報 → 対象
        "ecmwf_s51_2m_temperature_monthly_mean_1993-2016-11_L1-6.grib": True,               # ECMWF のハインドキャスト → 対象
    }
    for n in names:
        _touch(str(tmp_path / n), old)
    got = {os.path.basename(p) for p, _ in cleanup.grib_targets(time.time(), 45, 45)}
    assert got == {n for n, d in names.items() if d}


def test_新しいファイルは残す(tmp_path, monkeypatch):
    monkeypatch.setattr(cleanup, "C3S", str(tmp_path))
    _touch(str(tmp_path / "ecmwf_s51_2m_temperature_monthly_mean_1993-2016-11_L1-6.grib"), 10)
    _touch(str(tmp_path / "ecmwf_s51_2m_temperature_monthly_mean_2026-11_L1-6.grib"), 10)
    assert cleanup.grib_targets(time.time(), 45, 45) == []
    # ハインドキャストだけ短くすると、それだけ対象になる
    assert [os.path.basename(p) for p, _ in cleanup.grib_targets(time.time(), 45, 5)] == ["ecmwf_s51_2m_temperature_monthly_mean_1993-2016-11_L1-6.grib"]
