"""jma_style.py（気象庁の速報と同じ表示形式の図）のテスト。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jma_style  # noqa: E402


def test_経度を指定の経度から始まる並びにそろえる():
    lon = np.arange(0, 360, 2.5)
    f = np.tile(lon, (3, 1))
    g, lo = jma_style._shift(f, lon, -30.0)
    assert lo[0] == -30.0 and lo[-1] == 327.5 and np.all(np.diff(lo) == 2.5)
    assert g[0][0] == 330.0 and g[0][12] == 0.0 and lo[12] == 0.0                         # 330°E の列が先頭（-30°）へ移り、値は経度と一緒に動く


def test_経度ラベル():
    assert jma_style._lon_label(0) == "0°" and jma_style._lon_label(180) == "180°"
    assert jma_style._lon_label(30) == "30°E" and jma_style._lon_label(330) == "30°W" and jma_style._lon_label(210) == "150°W"


def test_流線関数の極大は北半球でH南半球でL():
    lat = np.arange(60, -60.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    f = 50 * np.exp(-(((la - 30) / 8) ** 2 + ((lo - 100) / 10) ** 2)) - 50 * np.exp(-(((la + 30) / 8) ** 2 + ((lo - 200) / 10) ** 2))
    marks = {(round(y), round(x)): m for y, x, m in jma_style.extrema(f, lat, lon, 5.0)}
    assert marks.get((30, 100)) == "H" and marks.get((-30, 200)) == "H"                # 北の極大=H・南の極小=H（高気圧性）
    f2 = -f
    marks2 = {(round(y), round(x)): m for y, x, m in jma_style.extrema(f2, lat, lon, 5.0)}
    assert marks2.get((30, 100)) == "L" and marks2.get((-30, 200)) == "L"


def test_発散風は速度ポテンシャルの勾配():
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    chi = np.tile(np.sin(np.deg2rad(lon)), (len(lat), 1))                              # 10⁶ m²/s
    u, v = jma_style.divergent_wind(chi, lat, lon)
    i = int(np.argmin(np.abs(lat)))                                                   # 赤道・経度0付近: u = (1/a)∂χ/∂λ = 1e6/6.371e6
    assert abs(u[i, 0] - 1e6 / 6.371e6) < 2e-3 and abs(v[i, 0]) < 1e-9
