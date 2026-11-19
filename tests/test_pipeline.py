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
    names = [n for n, _ in s]
    assert names[0] == "月平均の取得" and names[-3] == "一覧の更新" and names[-2] == "公開サイトの更新" and names[-1] == "古い取得ファイルの整理"
    assert any("--lagged" in c for _, c in s)
    assert all(c[-1] != "" for _, c in s)
    c4 = pipeline.cps4_steps(2026, 12)
    assert "--bulk" in c4[0][1] and "--month" in c4[1][1] and c4[-2][0] == "公開サイトの更新" and "--publish" in c4[-2][1] and c4[-1][0] == "古い取得ファイルの整理"


def test_dryrunは何も実行しない(tmp_path):
    ok, rec = pipeline.run_steps(pipeline.cfs_steps("20261113"), str(tmp_path / "x.log"), dry=True)
    assert ok and all(r["結果"] == "dry-run" for r in rec) and not (tmp_path / "x.log").exists()


def test_失敗した手順で止まる(tmp_path):
    steps = [("ok", [sys.executable, "-c", "pass"]), ("ng", [sys.executable, "-c", "import sys; sys.exit(3)"]),
             ("後続", [sys.executable, "-c", "pass"])]
    ok, rec = pipeline.run_steps(steps, str(tmp_path / "x.log"))
    assert not ok and [r["手順"] for r in rec] == ["ok", "ng"] and "終了コード3" in rec[1]["結果"]


def test_縮小係数は校正した季節の外では使わない(tmp_path, monkeypatch):
    import calib
    real = calib.load(charts.CAL_PATH)                       # 実データの11月分だけを使う（校正の月が増えても結果が変わらないように）
    sub = {"version": 2, "cfs": {"20261112": real["cfs"]["20261112"]}, "cps4": {"11": real["cps4"]["11"]}}
    calib.save(sub, str(tmp_path / "c.json"))
    monkeypatch.setattr(charts, "CAL_PATH", str(tmp_path / "c.json"))
    assert charts.calib_valid(None)                         # 指定なしは従来どおり有効
    assert charts.calib_valid("20261112") and charts.calib_valid("20261120") and charts.calib_valid("20261103")
    assert not charts.calib_valid("20261201") and not charts.calib_valid("20270312")
    assert charts.load_alpha("W1", "asia", "t2m", "20261112") is not None
    assert charts.load_alpha("W1", "asia", "t2m", "20270312") is None
    assert not charts.has_var_alpha("W1", "t2m", "20270312")
    assert charts.calib_valid("20261101", "cps4") and not charts.calib_valid("20261201", "cps4")


def test_校正の選択は季節で切り替わる(tmp_path):
    import calib
    cal = {"version": 2,
           "cfs": {"20261112": {"alpha": {"W1": {"asia": 0.7, "global": 0.7}}}, "20261215": {"alpha": {"W1": {"asia": 0.3, "global": 0.3}}}},
           "cps4": {"11": {"alpha_var": {}}, "12": {"alpha_var": {}}}}
    assert calib.cfs_slot(cal, "20261120")[0] == "20261112"
    assert calib.cfs_slot(cal, "20261205")[0] == "20261215"          # 12/5 は 12/15 に近い
    assert calib.cfs_slot(cal, "20270312")[0] is None                # 3月の校正が無い
    assert calib.cfs_slot(cal, "20270105")[0] is None                # 12/15 から21日（範囲15日の外）
    wrap = {"version": 2, "cfs": {"20261228": {}}, "cps4": {}}
    assert calib.cfs_slot(wrap, "20270105")[0] == "20261228"          # 年をまたいでも月日で近い（8日）
    assert calib.cps4_slot(cal, 12)[0] == "12" and calib.cps4_slot(cal, 3)[0] is None


def test_校正の更新は統合される(tmp_path):
    import calib
    p = str(tmp_path / "c.json")
    calib.update_cfs("20261215", meta={"a": 1}, alpha={"W1": {"asia": 0.5, "global": 0.5}}, path=p)
    calib.update_cfs("20261215", meta={"b": 2}, alpha_var={"prate": {"W1": {"asia": 0.2, "global": 0.2}}}, path=p)
    c = calib.load(p)["cfs"]["20261215"]
    assert c["meta"]["a"] == 1 and c["meta"]["b"] == 2 and c["alpha"]["W1"]["asia"] == 0.5
    assert c["alpha_var"]["prate"]["W1"]["asia"] == 0.2
    calib.update_cps4(12, alpha_var={"t2m": {"L1": {"asia": 0.4, "global": 0.4}}}, path=p)
    assert calib.load(p)["cps4"]["12"]["meta"]["開始月"] == 12


def test_旧形式は新形式へ移行される():
    import calib
    old = {"メタ": {"対象初期日": "20261112"}, "alpha": {"W1": {"asia": 0.7}, "L1": {"asia": 0.4}},
           "alpha_var": {"prate": {"W1": {"asia": 0.5}, "L1": {"asia": 0.3}}}, "メタ_CPS4": {"開始月": 11}}
    n = calib.migrate_v1(old)
    assert set(n["cfs"]["20261112"]["alpha"]) == {"W1"}
    assert set(n["cfs"]["20261112"]["alpha_var"]["prate"]) == {"W1"}
    assert set(n["cps4"]["11"]["alpha_var"]["prate"]) == {"L1"}


def test_校正の手順の構成():
    import calibrate
    s = calibrate.steps_for(12)
    assert [n.split(":")[0] for n, _ in s] == ["CFS 12月"] * 4 + ["CPS4 12月開始"] * 2
    assert "20261215" in s[0][1] and "--hind-only" in s[4][1] and s[5][1][-3:] == ["--month", "12", "--write"]
    assert all("--write" in c for n, c in s if "照合" in n)


def test_校正の手順は失敗したら待ってやり直す(tmp_path):
    import calibrate
    flag = tmp_path / "flag"
    # 1回目は失敗（フラグを作る）、2回目は成功する手順
    cmd = [sys.executable, "-c", f"import os,sys; p=r'{flag}'; ok=os.path.exists(p); open(p,'w').close(); sys.exit(0 if ok else 3)"]
    ok, rec, stopped = calibrate.run_with_retry([("テスト取得", cmd)], str(tmp_path / "l.log"), wait=0)
    assert ok and [r["結果"] for r in rec] == ["失敗(終了コード3)", "成功"]


def test_ログが増えない手順は打ち切って失敗にする(tmp_path):
    import time
    t0 = time.time()
    ok, rec = pipeline.run_steps([("固まる", [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(60)"])],
                                 str(tmp_path / "l.log"), stall_sec=2, poll=0.5)
    assert not ok and "終了コード124" in rec[0]["結果"] and time.time() - t0 < 20
    assert "見張り" in (tmp_path / "l.log").read_text(encoding="utf-8")


def test_期限が来たら取得を打ち切って中断する(tmp_path):
    import calibrate
    import time
    until = time.time() + 2
    t0 = time.time()
    ok, rec, stopped = calibrate.run_with_retry(
        [("テスト取得", [sys.executable, "-c", "import time; print('s', flush=True); time.sleep(60)"]),
         ("次の手順", [sys.executable, "-c", "print(1)"])], str(tmp_path / "l.log"), wait=0, until=until)
    assert not ok and stopped and len(rec) == 1 and time.time() - t0 < 30
