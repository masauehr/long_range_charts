"""ecmwf_dyn.py（極を含まない1°格子→極を含む格子→元の格子）のテスト。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dyn_solver  # noqa: E402
import ecmwf_dyn  # noqa: E402

LAT = np.arange(89.5, -89.6, -1.0)                      # ECMWF の1°格子（緯度は中心値・極を含まない）
LON = np.arange(0.0, 360.0, 1.0)


def test_定数と緯度の線形関数は往復で保たれる():
    a = np.broadcast_to(2.0 + 0.01 * LAT[:, None], (len(LAT), len(LON))).astype("float32")
    b = ecmwf_dyn.from_pole_grid(ecmwf_dyn.to_pole_grid(a, LAT), LAT)
    assert b.shape == a.shape
    assert np.allclose(a[2:-2], b[2:-2], atol=1e-4)          # 端の2行を除いて一致（端は極への外挿で少しずれうる）


def test_極なし格子の風からも流線関数が解析解に近い():
    # ψ = A cos²φ sinφ cos(2λ)（波数2・全球平均0）。u = -(1/a)∂ψ/∂φ、v = (1/(a cosφ))∂ψ/∂λ
    r = 6.371e6
    A = 3.0e6
    phi, lam = np.deg2rad(LAT)[:, None], np.deg2rad(LON)[None, :]
    psi = A * np.cos(phi) ** 2 * np.sin(phi) * np.cos(2 * lam)
    u = -(A / r) * (-2 * np.cos(phi) * np.sin(phi) ** 2 + np.cos(phi) ** 3) * np.cos(2 * lam)
    v = -(2 * A / r) * np.cos(phi) * np.sin(phi) * np.sin(2 * lam)
    uu, vv = ecmwf_dyn.to_pole_grid(u.astype("float32"), LAT), ecmwf_dyn.to_pole_grid(v.astype("float32"), LAT)
    p, _ = dyn_solver.streamfunction_potential(uu, vv, ecmwf_dyn.POLE_LAT)
    p = dyn_solver.remove_global_mean(p, ecmwf_dyn.POLE_LAT)
    got = ecmwf_dyn.from_pole_grid(p, LAT)
    err = np.sqrt(np.mean((got - psi) ** 2)) / np.sqrt(np.mean(psi ** 2))
    assert err < 0.10, err
