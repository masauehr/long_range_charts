"""公開サイト（GitHub Pages）用に _site/ を作る。**NOAA CFSv2 の図だけ**を載せる（JMA/MRI-CPS4・元データ・気象庁の参照は載せない）。

載せるもの: web/ の画面（index.html・board.html・app.js・board.js・style.css）、CFS 系列の図（最新の N 初期日）、公開用 manifest.json。
載せないもの: data/（GRIB・再解析）、cps4 の図、reference/、calibration.json、ログ。
図は output/ から _site/output/ へコピーする（画面は manifest の imgdir=output/ を相対参照）。

使い方:
  python build_site.py                  # _site/ を作る（最新6初期日）
  python build_site.py --keep 8         # 初期日の数を変える
  python build_site.py --publish        # _site/ を gh-pages ブランチへ1コミットで置き換えて push する（履歴を残さない）
公開は NOTICE.md の「公開前チェックリスト」に従う。CPS4（C3S）を載せるかは別の判断。
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import charts
import clim
import make_web

ROOT = clim.ROOT
SITE = os.path.join(ROOT, "_site")
PUBLIC_SERIES = ("cfs_week", "cfs_week_lag", "cfs_month")        # CPS4（C3S）は載せない
WEB_FILES = ["index.html", "board.html", "app.js", "board.js", "style.css"]
BRANCH = "gh-pages"


def public_manifest(keep, out_dir=charts.OUT):
    """CFS 系列だけ・最新 keep 初期日だけの manifest。imgdir は公開サイト内の相対パス。"""
    m = make_web.build(out_dir)
    series = []
    for s in m["series"]:
        if s["id"] not in PUBLIC_SERIES:
            continue
        s = dict(s)
        s["inits"] = s["inits"][:keep]                      # 新しい順なので先頭が最新
        if s["inits"]:
            series.append(s)
    return {"generated": m["generated"], "regions": m["regions"], "imgdir": "output/", "public": True, "series": series}


def build(keep=6, site=SITE, out_dir=charts.OUT):
    m = public_manifest(keep, out_dir)
    if os.path.isdir(site):
        shutil.rmtree(site)                                  # 自分が作った _site/ だけを作り直す（出力先を限定）
    os.makedirs(os.path.join(site, "output"))
    for f in WEB_FILES:
        dst = os.path.join(site, f)
        shutil.copy(os.path.join(ROOT, "web", f), dst)
        if f.endswith(".html"):                              # CPS4 を載せない公開版では、HTML からも C3S の出典欄を取り除く（JS無効でも出ない）
            t = open(dst, encoding="utf-8").read()
            t = re.sub(r'<span class="c3s">.*?</span>', "", t, flags=re.S)
            open(dst, "w", encoding="utf-8").write(t)
    files = sorted({fn for s in m["series"] for i in s["inits"] for fn in i["files"].values()})
    for fn in files:
        shutil.copy(os.path.join(out_dir, fn), os.path.join(site, "output", fn))
    with open(os.path.join(site, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    open(os.path.join(site, ".nojekyll"), "w").close()
    mb = sum(os.path.getsize(os.path.join(site, "output", fn)) for fn in files) / 1e6
    return m, files, mb


def check(site=SITE):
    """公開してはいけないものが入っていないか確かめる。問題の一覧を返す。"""
    bad = []
    for root, _, fs in os.walk(site):
        for f in fs:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, site)
            if f.startswith("cps4_") or f.endswith((".grib", ".grb", ".grb2", ".nc", ".npz", ".json")) and f != "manifest.json":
                bad.append(rel)
    m = json.load(open(os.path.join(site, "manifest.json"), encoding="utf-8"))
    if any(s["id"] == "cps4" for s in m["series"]):
        bad.append("manifest に cps4")
    return bad


def publish(site=SITE):
    """_site/ を gh-pages ブランチの唯一のコミットにして force push する（履歴は残さない＝リポジトリが膨らまない）。"""
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    tmp = tempfile.mkdtemp(prefix="lrc_pages_")
    work = os.path.join(tmp, "w")
    shutil.copytree(site, work)
    run = lambda *a: subprocess.run(a, cwd=work, check=True)
    run("git", "init", "-q", "-b", BRANCH)
    run("git", "add", "-A")
    run("git", "-c", "user.name=long_range_charts", "-c", "user.email=noreply@example.com", "commit", "-q", "-m",
        f"公開サイトを更新 {dt.datetime.now():%Y-%m-%d %H:%M}（NOAA CFSv2 の図のみ）")
    run("git", "push", "-q", "--force", remote, f"{BRANCH}:{BRANCH}")
    shutil.rmtree(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=6, help="載せる初期日の数（系列ごと・新しい順）")
    ap.add_argument("--publish", action="store_true", help="gh-pages へ push する")
    a = ap.parse_args()
    m, files, mb = build(a.keep)
    for s in m["series"]:
        print(f"  {s['id']}: 初期日 {[i['init'] for i in s['inits']]}")
    print(f"_site/ を作成: 図 {len(files)}枚・{mb:.1f}MB")
    bad = check()
    if bad:
        print("公開してはいけないものが含まれている:", bad[:10], file=sys.stderr)
        sys.exit(1)
    print("公開前チェック: CPS4・元データ・json(manifest以外) は含まれていない")
    if a.publish:
        publish()
        print(f"{BRANCH} へ push しました")


if __name__ == "__main__":
    main()
