"""風（u, v）から流線関数 ψ と速度ポテンシャル χ を求める（緯度経度格子・球面・追加ライブラリ不要）。

定義: u = −(1/a)∂ψ/∂φ + (1/(a cosφ))∂χ/∂λ,  v = (1/(a cosφ))∂ψ/∂λ + (1/a)∂χ/∂φ
      渦度 ζ = ∇²ψ,  発散 D = ∇²χ   （a: 地球半径・φ: 緯度・λ: 経度）
  → 北半球では ψ が正の所は高気圧性、負の所は低気圧性の循環（南半球は逆）。
  → χ が負の極小の所は発散（上層では対流が活発な側）、正の極大の所は収束。

方法: ζ と D を差分で作り、ポアソン方程式 ∇²ψ=ζ・∇²χ=D を解く。
  - 東西方向はフーリエ変換（波数 m ごとに独立）。m≥1 は南北方向の3重対角連立方程式（極で 0）を、格子ごとに一度だけ逆行列にして使い回す。
  - m=0（東西平均）は、東西平均風を南北に積分して直接求める（ψ0 = −a∫u0 dφ・χ0 = a∫v0 dφ・北極で 0）。
  - 極の行は、風が定義できないので ζ・D の計算から除く（ψ・χ の極の値は m=0 の積分値）。
定数項は不定なので、**全球の面積平均が0**になるようにそろえる（remove_global_mean）。**偏差（予報 − 気候値）で使う**こと。
入力は [..., 緯, 経]（緯度は等間隔・北→南または南→北、経度は等間隔・全周）。欠測（NaN）があれば、その場の結果は NaN。
"""
import numpy as np

A = 6.371e6                    # 地球半径（m）
_CACHE = {}


def _prep(lat, nlon):
    """格子ごとの前処理（逆行列）を作る。lat は度。戻り値は北→南にそろえた緯度（ラジアン）と m ごとの逆行列。"""
    key = (tuple(np.round(lat, 4)), nlon)
    if key in _CACHE:
        return _CACHE[key]
    phi = np.deg2rad(np.asarray(lat, float))
    n = len(phi)
    dphi = abs(phi[1] - phi[0])
    cosp = np.cos(phi)
    cosh = np.cos((phi[1:] + phi[:-1]) / 2)               # 半格子の cos
    inner = np.arange(1, n - 1)                            # 極を除く
    ms = np.arange(1, nlon // 2 + 1)
    inv = {}
    for m in ms:
        M = np.zeros((len(inner), len(inner)))
        for r, j in enumerate(inner):
            up, dn = cosh[j], cosh[j - 1]                  # j+1/2・j-1/2
            M[r, r] = -(up + dn) / (dphi ** 2 * A ** 2 * cosp[j]) - m ** 2 / (A ** 2 * cosp[j] ** 2)
            if r + 1 < len(inner):
                M[r, r + 1] = up / (dphi ** 2 * A ** 2 * cosp[j])
            if r - 1 >= 0:
                M[r, r - 1] = dn / (dphi ** 2 * A ** 2 * cosp[j])
        inv[m] = np.linalg.inv(M)
    _CACHE[key] = (phi, cosp, dphi, inner, inv)
    return _CACHE[key]


def _ddphi(f, dphi):
    """緯度方向の中心差分（端は片側）。f[..., 緯, 経]。dphi は格子の並び方向の緯度の増分（北→南なら負）。"""
    g = np.empty_like(f)
    g[..., 1:-1, :] = (f[..., 2:, :] - f[..., :-2, :]) / (2 * dphi)
    g[..., 0, :] = (f[..., 1, :] - f[..., 0, :]) / dphi
    g[..., -1, :] = (f[..., -1, :] - f[..., -2, :]) / dphi
    return g


def streamfunction_potential(u, v, lat):
    """u, v[..., 緯, 経]（m/s）→ (ψ, χ) [..., 緯, 経]（m²/s）。緯度は等間隔・北→南または南→北。"""
    u, v = np.asarray(u, "float64"), np.asarray(v, "float64")
    lat = np.asarray(lat, float)
    flip = lat[0] < lat[-1]                                # 南→北なら北→南へそろえる
    if flip:
        u, v, lat = u[..., ::-1, :], v[..., ::-1, :], lat[::-1]
    nlon = u.shape[-1]
    phi, cosp, dphi, inner, inv = _prep(lat, nlon)
    bad = ~np.isfinite(u).all(axis=(-2, -1)) | ~np.isfinite(v).all(axis=(-2, -1))
    u = np.where(np.isfinite(u), u, 0.0)
    v = np.where(np.isfinite(v), v, 0.0)
    cosc = cosp[:, None]
    # 経度方向の微分（フーリエ）
    uh, vh = np.fft.rfft(u, axis=-1), np.fft.rfft(v, axis=-1)
    m = np.arange(uh.shape[-1])
    dudl = np.fft.irfft(1j * m * uh, n=nlon, axis=-1)
    dvdl = np.fft.irfft(1j * m * vh, n=nlon, axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        zeta = (dvdl - _ddphi(u * cosc, -dphi)) / (A * cosc)
        div = (dudl + _ddphi(v * cosc, -dphi)) / (A * cosc)
    out = []
    for f, kind in ((zeta, "psi"), (div, "chi")):
        fh = np.fft.rfft(f[..., inner, :], axis=-1)        # [..., 内部緯度, 波数]
        sol = np.zeros_like(fh)
        for mm in range(1, fh.shape[-1]):
            if mm in inv:
                sol[..., mm] = np.einsum("ij,...j->...i", inv[mm], fh[..., :, mm])
        full = np.zeros(f.shape[:-2] + (len(phi), fh.shape[-1]), dtype=complex)
        full[..., inner, :] = sol
        field = np.fft.irfft(full, n=nlon, axis=-1)
        # 東西平均（m=0）は風の積分で求める
        if kind == "psi":
            z0 = -A * _cumtrap(u.mean(axis=-1), phi)
        else:
            z0 = A * _cumtrap(v.mean(axis=-1), phi)
        out.append(field + z0[..., :, None])
    psi, chi = out
    psi, chi = remove_global_mean(psi, lat), remove_global_mean(chi, lat)
    psi = np.where(bad[..., None, None], np.nan, psi)
    chi = np.where(bad[..., None, None], np.nan, chi)
    if flip:
        psi, chi = psi[..., ::-1, :], chi[..., ::-1, :]
    return psi.astype("float32"), chi.astype("float32")


def remove_global_mean(f, lat):
    """全球の面積平均（cos緯度の重み）を引く（定数項を「全球平均0」にそろえる。北極で0とする規約だと、東西平均風の偏差が南半球へ積算されて大きく出るため）。
    f[..., 緯, 経]・lat は度。何度掛けても同じ。"""
    w = np.cos(np.deg2rad(np.asarray(lat, float)))
    w = w / w.sum()
    m = np.tensordot(np.nanmean(f, axis=-1), w, axes=([-1], [0]))
    return (f - m[..., None, None]).astype(f.dtype)


def _cumtrap(f, phi):
    """北端から南へ向かう緯度 φ（ラジアン・減少）方向の累積台形積分 ∫_{φ_N}^{φ} f dφ'。f[..., 緯]。"""
    d = np.diff(phi)                                       # 負の値
    inc = 0.5 * (f[..., 1:] + f[..., :-1]) * d
    return np.concatenate([np.zeros(f.shape[:-1] + (1,)), np.cumsum(inc, axis=-1)], axis=-1)
