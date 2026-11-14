"""確率の縮小係数（calibration.json）の読み書きと、季節に合う校正の選択。

構造（version 2）:
  {"version": 2,
   "cfs":  {"20261112": {"meta": {...}, "alpha": {窓: {asia, global, acc_asia, acc_global}}, "alpha_var": {変数: {窓: {...}}}}, ...},
   "cps4": {"11": {"meta": {...}, "alpha_var": {変数: {窓: {...}}}}, ...}}
- CFS は校正した基準の初期日（YYYYMMDD）ごと。対象の初期日に**月日で最も近い**校正を、前後 DAYS 日以内なら使う（年は無視）。
- CPS4 は校正した開始月（"11" など）ごと。対象と同じ開始月の校正だけを使う。
- 校正が見つからないときは None（図は「未補正」と表示する）。
旧形式（version なし: メタ・alpha・alpha_var・メタ_CPS4 などが直下）は、読むときに自動で新形式へ変換する。
"""
import contextlib
import datetime as dt
import fcntl
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "calibration.json")
DAYS = 15                                   # 校正した初期日からこの日数以内の初期日に適用する（CFS）
CFS_NAMES = {"W1", "W2", "W3", "W4", "J28", "M1", "M2", "M3", "M4", "Q1"}
CPS4_NAMES = {"L1", "L2", "L3", "L4", "L5", "L6", "L2-4", "L1-3"}


def migrate_v1(old):
    """旧形式を新形式へ変換する（メモリ上）。"""
    cfs_meta = dict(old.get("メタ", {}))
    cfs_meta.update(old.get("メタ_CFS変数別", {}))
    key = cfs_meta.get("対象初期日", "20261112")
    cfs = {"meta": cfs_meta,
           "alpha": {k: v for k, v in old.get("alpha", {}).items() if k in CFS_NAMES},
           "alpha_var": {}}
    cps = {"meta": dict(old.get("メタ_CPS4", {})), "alpha_var": {}}
    for var, d in old.get("alpha_var", {}).items():
        c = {k: v for k, v in d.items() if k in CFS_NAMES}
        p = {k: v for k, v in d.items() if k in CPS4_NAMES}
        if c:
            cfs["alpha_var"][var] = c
        if p:
            cps["alpha_var"][var] = p
    month = str(cps["meta"].get("開始月", 11))
    return {"version": 2, "cfs": {key: cfs}, "cps4": {month: cps}}


def load(path=PATH):
    try:
        with open(path, encoding="utf-8") as f:
            cal = json.load(f)
    except (OSError, ValueError):
        return {"version": 2, "cfs": {}, "cps4": {}}
    return cal if cal.get("version") == 2 else migrate_v1(cal)


def save(cal, path=PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=1, sort_keys=True)


def _md_distance(a, b):
    """月日どうしの距離（日・年は無視・年をまたぐ）。"""
    d = abs((a.replace(year=2001) - b.replace(year=2001)).days)
    return min(d, 365 - d)


def cfs_slot(cal, target, days=DAYS):
    """対象の初期日に最も近い CFS 校正（キー, 中身）。無い・範囲外なら (None, None)。target=None なら最初の校正。"""
    slots = cal.get("cfs", {})
    if not slots:
        return None, None
    if target is None:
        k = sorted(slots)[0]
        return k, slots[k]
    t = dt.datetime.strptime(target, "%Y%m%d").date()
    best = min(slots, key=lambda k: _md_distance(t, dt.datetime.strptime(k, "%Y%m%d").date()))
    if _md_distance(t, dt.datetime.strptime(best, "%Y%m%d").date()) > days:
        return None, None
    return best, slots[best]


def cps4_slot(cal, month):
    """対象の開始月の CPS4 校正（キー, 中身）。無ければ (None, None)。month=None なら最初の校正。"""
    slots = cal.get("cps4", {})
    if month is None:
        if not slots:
            return None, None
        k = sorted(slots)[0]
        return k, slots[k]
    k = str(int(month))
    return (k, slots[k]) if k in slots else (None, None)


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


@contextlib.contextmanager
def _lock(path):
    """読み込み→統合→保存の間、他の校正プロセスが同時に書かないようにする（ロックファイルを使う）。"""
    with open(path + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update_cfs(target, meta=None, alpha=None, alpha_var=None, path=PATH):
    """CFS の校正（基準の初期日 target）に、メタ・alpha（2m気温）・alpha_var（変数別）を統合して保存する。"""
    with _lock(path):
        cal = load(path)
        slot = cal["cfs"].setdefault(target, {"meta": {}, "alpha": {}, "alpha_var": {}})
        _merge(slot, {"meta": meta or {}, "alpha": alpha or {}, "alpha_var": alpha_var or {}})
        slot["meta"]["対象初期日"] = target
        save(cal, path)


def update_cps4(month, meta=None, alpha_var=None, path=PATH):
    """CPS4 の校正（開始月 month）に、メタ・alpha_var（変数別）を統合して保存する。"""
    with _lock(path):
        cal = load(path)
        slot = cal["cps4"].setdefault(str(int(month)), {"meta": {}, "alpha_var": {}})
        _merge(slot, {"meta": meta or {}, "alpha_var": alpha_var or {}})
        slot["meta"]["開始月"] = int(month)
        save(cal, path)
