"""地点の分布図（過去の分布と今回の予報メンバー）用のデータを集めて JSON に書く。

気候値（過去のサンプル）と今回の予報メンバーを、東アジアの 2.5° 格子の各地点ごとにヒストグラム（同じ階級）にする。
weekly.py・charts.py・cps4.py が作図のついでに add() し、最後に write() する。画面の「地点の数値」が読む（output/dist_{系列}_{初期日}.json）。
ほかのモジュールを import しない（循環を避けるため）。
"""
import json
import os

import numpy as np

BOX = (8, 62, 95, 175)                     # 東アジア（北緯・東経）
NB = 16                                    # 階級の数
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


class Collector:
    def __init__(self):
        self.d = {}

    def add(self, var, period, samples, members, lat, lon):
        """samples[N, 緯, 経]（気候値のサンプル）と members[M, 緯, 経]（今回の予報）を、地点ごとのヒストグラムにして蓄える。"""
        step = 2 if len(lat) > 100 else 1                    # CPS4 は 1.25° → 2.5°
        la, lo = lat[::step], lon[::step]
        yi = np.where((la >= BOX[0]) & (la <= BOX[1]))[0]
        xi = np.where((lo >= BOX[2]) & (lo <= BOX[3]))[0]

        def cut(a):
            return a[:, ::step, ::step][:, yi][:, :, xi].reshape(a.shape[0], -1)
        s, m = cut(np.asarray(samples, "float64")), cut(np.asarray(members, "float64"))
        cells = s.shape[1]
        los, his = np.zeros(cells), np.zeros(cells)
        cc, fc = np.zeros((cells, NB), "int32"), np.zeros((cells, NB), "int32")
        for c in range(cells):
            sv, mv = s[:, c][np.isfinite(s[:, c])], m[:, c][np.isfinite(m[:, c])]
            if len(sv) == 0:
                continue
            allv = np.concatenate([sv, mv])
            lo_, hi_ = float(allv.min()), float(allv.max())
            if hi_ - lo_ < 1e-9:
                hi_ = lo_ + 1e-6
            edges = np.linspace(lo_, hi_, NB + 1)
            los[c], his[c] = lo_, hi_
            cc[c] = np.histogram(sv, edges)[0]
            fc[c] = np.histogram(mv, edges)[0] if len(mv) else 0
        self.d.setdefault(var, {})[period] = dict(
            n=int(np.nanmax((np.isfinite(s)).sum(0))), m=int(m.shape[0]), lo=[round(float(x), 3) for x in los],
            hi=[round(float(x), 3) for x in his], cc=cc.ravel().tolist(), fc=fc.ravel().tolist())
        self.grid = ([float(x) for x in la[yi]], [float(x) for x in lo[xi]])

    def write(self, sid, init, out_dir=OUT):
        if not self.d:
            return None
        path = os.path.join(out_dir, f"dist_{sid}_{init}.json")
        os.makedirs(out_dir, exist_ok=True)
        vars_ = dict(self.d)
        if os.path.exists(path):                             # 同じ系列・初期日の既存ファイルがあれば変数を統合する（dyn.py など別の作図が足した変数を消さない）
            try:
                old = json.load(open(path, encoding="utf-8"))
                if old.get("init") == init and old.get("nb") == NB and old.get("lat") == self.grid[0] and old.get("lon") == self.grid[1]:
                    vars_ = {**old.get("vars", {}), **self.d}
            except ValueError:
                pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(series=sid, init=init, nb=NB, lat=self.grid[0], lon=self.grid[1], vars=vars_), f, ensure_ascii=False, separators=(",", ":"))
        print(f"分布図のデータ: {os.path.basename(path)}（{os.path.getsize(path) / 1e3:.0f}KB）", flush=True)
        return path
