"""dyn_solver.py（流線関数・速度ポテンシャル）の精度のテスト。解析的な ψ・χ から風を作り、復元できるか確かめる。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dyn_solver  # noqa: E402

A = dyn_solver.A


def _fields(lat, lon):
    phi = np.deg2rad(lat)[:, None]
    lam = np.deg2rad(lon)[None, :]
    P, Q, R = 1e7, 4e6, 5e6
    cp, sp = np.cos(phi), np.sin(phi)
    psi = P * cp ** 2 * sp * np.cos(2 * lam) + R * sp * cp ** 2
    chi = Q * cp ** 3 * np.cos(3 * lam + 0.5)
    dpsi_dphi = P * (-2 * cp * sp ** 2 + cp ** 3) * np.cos(2 * lam) + R * (cp ** 3 - 2 * cp * sp ** 2)
    dpsi_dlam = -2 * P * cp ** 2 * sp * np.sin(2 * lam)
    dchi_dphi = -3 * Q * cp ** 2 * sp * np.cos(3 * lam + 0.5)
    dchi_dlam = -3 * Q * cp ** 3 * np.sin(3 * lam + 0.5)
    with np.errstate(divide="ignore", invalid="ignore"):
        u = -dpsi_dphi / A + dchi_dlam / (A * cp)
        v = dpsi_dlam / (A * cp) + dchi_dphi / A
    u[0], u[-1], v[0], v[-1] = 0.0, 0.0, 0.0, 0.0                     # 極の行は使われない
    return psi, chi, u, v


def _check(lat, lon, tol):
    psi, chi, u, v = _fields(lat, lon)
    p, c = dyn_solver.streamfunction_potential(u, v, lat)
    sel = np.abs(lat) <= 80
    for name, got, ref in (("psi", p, psi), ("chi", c, chi)):
        err = np.sqrt(np.mean((got[sel] - ref[sel]) ** 2)) / np.sqrt(np.mean(ref[sel] ** 2))
        assert err < tol, (name, err)


def test_2_5度格子で流線関数と速度ポテンシャルを復元できる():
    _check(np.arange(90, -90.1, -2.5), np.arange(0, 360, 2.5), 0.04)


def test_1_25度格子ではさらに精度が上がる():
    _check(np.arange(90, -90.1, -1.25), np.arange(0, 360, 1.25), 0.012)


def test_南北どちらの向きの緯度でも同じ結果():
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    _, _, u, v = _fields(lat, lon)
    p1, c1 = dyn_solver.streamfunction_potential(u, v, lat)
    p2, c2 = dyn_solver.streamfunction_potential(u[::-1], v[::-1], lat[::-1])
    assert np.allclose(p1, p2[::-1], rtol=1e-4, atol=1e3) and np.allclose(c1, c2[::-1], rtol=1e-4, atol=1e3)


def test_複数の場を一度に処理でき欠測はNaNになる():
    lat = np.arange(90, -90.1, -2.5)
    lon = np.arange(0, 360, 2.5)
    _, _, u, v = _fields(lat, lon)
    U = np.stack([u, 2 * u, u])
    V = np.stack([v, 2 * v, v])
    U[2, 10, 10] = np.nan
    p, c = dyn_solver.streamfunction_potential(U, V, lat)
    assert p.shape == U.shape and np.isnan(p[2]).all() and np.allclose(p[1], 2 * p[0], rtol=1e-4, atol=1e3)
