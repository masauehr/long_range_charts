"""waf.py（波の活動度フラックス）のテスト。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import waf  # noqa: E402


def _grid():
    lat = np.arange(80, -80.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    return lat, lon


def test_西風の中を東西波数mの波のフラックスは東向きで解析値と合う():
    lat, lon = _grid()
    phi = np.deg2rad(lat)[:, None]
    lam = np.deg2rad(lon)[None, :]
    amp, m = 5.0, 4                                                   # ψ' = amp·cos(mλ)·cos²φ（10⁶ m²/s）
    psi = amp * np.cos(m * lam) * np.cos(phi) ** 2
    u = np.full(psi.shape, 20.0)
    v = np.zeros(psi.shape)
    wx, wy = waf.wave_activity_flux(psi, u, v, lat, lon, p_hpa=200.0)
    i = int(np.argmin(np.abs(lat - 45)))
    # 解析値: Wx = (p cosφ/(2|U|))·U/(a² cos²φ)·(ψλ² − ψψλλ) = p/(2 a² cosφ)·A²m²cos⁴φ（東西平均は ψλ²−ψψλλ = A²m²cos⁴φ·1）
    expect = 0.2 / (2 * waf.A ** 2 * np.cos(np.deg2rad(45))) * (amp * 1e6) ** 2 * m ** 2 * np.cos(np.deg2rad(45)) ** 4
    got = np.nanmean(wx[i])
    assert got > 0 and abs(got - expect) / expect < 0.05, (got, expect)


def test_基本場の西風が弱い所は描かない():
    lat, lon = _grid()
    psi = np.ones((len(lat), len(lon)))
    u = np.full(psi.shape, 1.0)                                       # 弱い風
    wx, wy = waf.wave_activity_flux(psi, u, np.zeros(psi.shape), lat, lon, min_u=3.0)
    assert np.isnan(wx).all() and np.isnan(wy).all()


def test_流線関数から風を作る():
    lat, lon = _grid()
    phi = np.deg2rad(lat)[:, None]
    psi = np.tile(-np.sin(phi) * waf.A * 10.0 * 1e-6, (1, len(lon)))   # u = −(1/a)∂ψ/∂φ = 10 cosφ（m/s）
    u, v = waf.wind_from_psi_chi(psi, np.zeros_like(psi), lat, lon)
    i = int(np.argmin(np.abs(lat - 30)))
    assert abs(u[i, 0] - 10 * np.cos(np.deg2rad(30))) < 0.15 and abs(v[i, 0]) < 1e-6
