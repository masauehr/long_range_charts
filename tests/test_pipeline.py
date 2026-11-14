"""pipeline.py と、縮小係数の有効範囲ガードのテスト。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import charts  # noqa: E402
import pipeline  # noqa: E402


def test_最新の完全な初期日を遡って探す():
    ok = {"20261112"}
    got = pipeline.latest_complete_init(dt.date(2026, 11, 14), back=7, check=lambda d: d in ok)
    assert got == "20261112"
    assert pipeline.latest_complete_init(dt.date(2026, 11, 14), back=1, check=lambda d: False) is None


def test_手順の構成():
    s = pipeline.cfs_steps("20261113")
    assert [n for n, _ in s][0] == "月平均の取得" and [n for n, _ in s][-1] == "一覧の更新"
    assert any("--lagged" in c for _, c in s)
    assert all(c[-1] != "" for _, c in s)
    c4 = pipeline.cps4_steps(2026, 12)
    assert "--bulk" in c4[0][1] and "--month" in c4[1][1]


def test_dryrunは何も実行しない(tmp_path):
    ok, rec = pipeline.run_steps(pipeline.cfs_steps("20261113"), str(tmp_path / "x.log"), dry=True)
    assert ok and all(r["結果"] == "dry-run" for r in rec) and not (tmp_path / "x.log").exists()


def test_失敗した手順で止まる(tmp_path):
    steps = [("ok", [sys.executable, "-c", "pass"]), ("ng", [sys.executable, "-c", "import sys; sys.exit(3)"]),
             ("後続", [sys.executable, "-c", "pass"])]
    ok, rec = pipeline.run_steps(steps, str(tmp_path / "x.log"))
    assert not ok and [r["手順"] for r in rec] == ["ok", "ng"] and "終了コード3" in rec[1]["結果"]


def test_縮小係数は校正した季節の外では使わない():
    assert charts.calib_valid(None)                         # 指定なしは従来どおり有効
    assert charts.calib_valid("20261112") and charts.calib_valid("20261120") and charts.calib_valid("20261103")
    assert not charts.calib_valid("20261201") and not charts.calib_valid("20270312")
    assert charts.load_alpha("W1", "asia", "t2m", "20261112") is not None
    assert charts.load_alpha("W1", "asia", "t2m", "20270312") is None
    assert not charts.has_var_alpha("W1", "t2m", "20270312")
    assert charts.calib_valid("20261101", "cps4") and not charts.calib_valid("20261201", "cps4")
