"""ロスビー波の波の活動度フラックス（Takaya and Nakamura 2001 の定常ロスビー波用・水平成分）を、流線関数の偏差と気候場から求める。

W = (p cosφ / (2|U|)) × [ U/(a²cos²φ) (ψ'λ² − ψ'ψ'λλ) + V/(a²cosφ) (ψ'λψ'φ − ψ'ψ'λφ) ,
                          U/(a²cosφ) (ψ'λψ'φ − ψ'ψ'λφ) + V/a² (ψ'φ² − ψ'ψ'φφ) ]
  ψ': 流線関数の偏差（m²/s）  U, V: 気候場の風（m/s）  p: 気圧/1000hPa（200hPa なら 0.2）  単位 m²/s²。
  W は波のエネルギー（波の活動度）の伝わる向き。基本場の西風が弱い所（|U| が小さい所）は理論が成り立たないので描かない。
気候場の風は、気候値の流線関数 ψ と速度ポテンシャル χ から作る: u = −(1/a)∂ψ/∂φ + (1/(a cosφ))∂χ/∂λ・v = (1/(a cosφ))∂ψ/∂λ + (1/a)∂χ/∂φ。
入力は [緯, 経] の配列（緯度は北→南または南→北・経度は等間隔で全周）。ψ・χ は 10⁶ m²/s（このプロジェクトの規約）。
"""
import numpy as np

A = 6.371e6


def _ddlam(f, dl):
    return (np.roll(f, -1, axis=1) - np.roll(f, 1, axis=1)) / (2 * dl)


def _d2dlam2(f, dl):
    return (np.roll(f, -1, axis=1) - 2 * f + np.roll(f, 1, axis=1)) / dl ** 2


def wind_from_psi_chi(psi, chi, lat, lon):
    """流線関数・速度ポテンシャル（10⁶ m²/s）から風 (u, v)（m/s）。"""
    phi = np.deg2rad(lat)
    dl = np.deg2rad(lon[1] - lon[0])
    psi, chi = np.asarray(psi, "float64") * 1e6, np.asarray(chi, "float64") * 1e6
    cos = np.cos(phi)[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = -np.gradient(psi, phi, axis=0) / A + _ddlam(chi, dl) / (A * cos)
        v = _ddlam(psi, dl) / (A * cos) + np.gradient(chi, phi, axis=0) / A
    return u, v


def wave_activity_flux(psi_anom, u_clim, v_clim, lat, lon, p_hpa=200.0, min_u=3.0):
    """戻り値: (Wx, Wy)（m²/s²）。|U|<min_u の所と、極に近い所（|lat|>80）は NaN。"""
    phi = np.deg2rad(lat)
    dl = np.deg2rad(lon[1] - lon[0])
    psi = np.asarray(psi_anom, "float64") * 1e6                       # 偏差（m²/s）
    cos = np.cos(phi)[:, None]
    p = p_hpa / 1000.0
    psil = _ddlam(psi, dl)
    psip = np.gradient(psi, phi, axis=0)
    psill = _d2dlam2(psi, dl)
    psipp = np.gradient(psip, phi, axis=0)
    psilp = np.gradient(psil, phi, axis=0)
    spd = np.hypot(u_clim, v_clim)
    with np.errstate(divide="ignore", invalid="ignore"):
        fac = p * cos / (2 * spd)
        wx = fac * (u_clim / (A ** 2 * cos ** 2) * (psil ** 2 - psi * psill) + v_clim / (A ** 2 * cos) * (psil * psip - psi * psilp))
        wy = fac * (u_clim / (A ** 2 * cos) * (psil * psip - psi * psilp) + v_clim / A ** 2 * (psip ** 2 - psi * psipp))
    bad = (spd < min_u) | (np.abs(lat)[:, None] > 80)
    wx[bad], wy[bad] = np.nan, np.nan
    return wx, wy
