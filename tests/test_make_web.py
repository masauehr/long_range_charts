"""make_web.py の単体テスト（空のPNGファイル名だけで manifest を作る）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import make_web  # noqa: E402


def test_ファイル名の分類():
    c = make_web.classify
    assert c("cfsv2_20261112_t2m_W1_asia.png") == ("cfs_week", "20261112", "t2m", "W1", "asia")
    assert c("cfsv2_20261112_t2m_W1_asia_lag.png") == ("cfs_week_lag", "20261112", "t2m", "W1", "asia")
    assert c("cfsv2_20261112_pot5_M2_global.png") == ("cfs_month", "20261112", "pot5", "M2", "global")
    assert c("cps4_20261101_sst_L2-4_global.png") == ("cps4", "20261101", "sst", "L2-4", "global")
    assert c("cfsv2_20261112_t2m_M1_asia_lag.png") is None          # 月平均のラグ版は無い
    assert c("readme.txt") is None


def test_manifestの形(tmp_path):
    for fn in ["cfsv2_20261112_t2m_W1_asia.png", "cfsv2_20261112_t2m_M1_global.png", "cps4_20261101_t2m_L2-4_asia.png",
               "cps4_20261101_t2m_L1_asia.png", "ignore.png"]:
        (tmp_path / fn).write_bytes(b"")
    m = make_web.build(str(tmp_path))
    ids = [s["id"] for s in m["series"]]
    assert ids == ["cfs_week", "cfs_month", "cps4"]                  # 定義順・空の系列は除く
    cps = m["series"][2]["inits"][0]
    assert cps["label"] == "2026年11月1日基準"
    assert cps["periods"]["L2-4"] == "12〜2月の3か月平均"
    assert cps["files"]["t2m|L2-4|asia"] == "cps4_20261101_t2m_L2-4_asia.png"
    assert m["series"][0]["inits"][0]["periods"]["W1"] == "予報1〜7日目（11/12〜11/18）の平均"


def test_気候値の図と地点の数値がmanifestに載る(tmp_path):
    out = tmp_path
    for fn in ["cfsv2_20261116_t2m_W1_asia.png", "cfsv2_20261116_t2m_W1_asia_lag.png", "clim_cfs_week_20261116_t2m_W1_asia.png", "pt_cfs_week_20261116.json"]:
        (out / fn).write_bytes(b"x")
    m = make_web.build(str(out))
    by = {s["id"]: s["inits"][0] for s in m["series"]}
    assert by["cfs_week"]["clim_files"] == {"t2m|W1|asia": "clim_cfs_week_20261116_t2m_W1_asia.png"}
    assert by["cfs_week"]["points"] == "pt_cfs_week_20261116.json"
    assert by["cfs_week_lag"]["clim_files"]["t2m|W1|asia"] == "clim_cfs_week_20261116_t2m_W1_asia.png"     # ラグ版は4メンバー版の気候値を使う
    assert "points" not in by["cfs_week_lag"]
