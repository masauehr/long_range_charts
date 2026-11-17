"""公開サイト（GitHub Pages）用に _site/ を作る。NOAA CFSv2 と JMA/MRI-CPS4（C3S 経由）の**図だけ**を載せる（元データ・気象庁の公式予報の参照は載せない）。

載せるもの: web/ の画面（index.html・board.html・app.js・board.js・style.css）、CFS・CPS4 の図（最新の N 初期日）、公開用 manifest.json。
載せないもの: data/（GRIB・再解析）、reference/、calibration.json、ログ。
図は output/ から _site/output/ へコピーする（画面は manifest の imgdir=output/ を相対参照）。

使い方:
  python build_site.py                  # _site/ を作る（最新6初期日）
  python build_site.py --keep 8         # 初期日の数を変える
  python build_site.py --publish        # _site/ を gh-pages ブランチへ1コミットで置き換えて push する（履歴を残さない）
公開は NOTICE.md の「公開前チェックリスト」に従う。CPS4 の出典欄（Copernicus・免責）は HTML に残す。
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
import md2html

ROOT = clim.ROOT
SITE = os.path.join(ROOT, "_site")
PUBLIC_SERIES = ("cfs_week", "cfs_week_lag", "cfs_month")        # **JMA/MRI-CPS4（C3S 経由）は公開しない**（2026-11-17 ユーザー決定）。JMA のデータで描く図はローカル版のみ
PUBLISH_ENSO = True         # エルニーニョ監視ページを公開する（2026-11-17 ユーザー承認）。False にするとページ・図・リンクを公開サイトから外す。気象庁の見通しは常に載せない
WEB_FILES = ["index.html", "board.html", "guide.html", "manual.html", "jma.html", "jma.js", "telecon.html", "telecon.js", "app.js", "board.js", "style.css"] + (["enso.html", "enso.js"] if PUBLISH_ENSO else [])
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


def write_public_enso(site, out_dir):
    """エルニーニョ監視の公開用 enso.json と図を _site/ に置く。**気象庁の公式の見通し（jma）は載せない**（ローカルのみ）。"""
    src = os.path.join(ROOT, "web", "enso.json")
    if not os.path.exists(src):
        return []
    d = json.load(open(src, encoding="utf-8"))
    d.pop("jma", None)
    if "cps4" not in PUBLIC_SERIES:                          # CPS4（JMA）の予測は公開しない（NOAA の CFSv2 の予測と観測の図は公開する）
        d["forecasts"] = [f for f in d.get("forecasts", []) if f.get("source") == "cfs"]
    d["imgdir"] = "output/"
    imgs = [d["obs_image"]] + [f["image"] for f in d.get("forecasts", [])]
    imgs = [f for f in imgs if os.path.exists(os.path.join(out_dir, f))]
    for f in imgs:
        shutil.copy(os.path.join(out_dir, f), os.path.join(site, "output", f))
    with open(os.path.join(site, "enso.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return imgs


def build(keep=6, site=SITE, out_dir=charts.OUT):
    m = public_manifest(keep, out_dir)
    if os.path.isdir(site):
        shutil.rmtree(site)                                  # 自分が作った _site/ だけを作り直す（出力先を限定）
    os.makedirs(os.path.join(site, "output"))
    for md, out_name, title, links in make_web.DOCS:        # ガイド（GUIDE.md）・操作マニュアル（MANUAL.md）を最新にしてから載せる
        with open(os.path.join(ROOT, "web", out_name), "w", encoding="utf-8") as f:
            f.write(md2html.convert(open(os.path.join(ROOT, md), encoding="utf-8").read(), title=title, links=links))
    for f in WEB_FILES:
        dst = os.path.join(site, f)
        shutil.copy(os.path.join(ROOT, "web", f), dst)
        if f.endswith(".html") and not PUBLISH_ENSO:         # 未公開の間は、画面の「エルニーニョ監視」リンクを取り除く
            t = open(dst, encoding="utf-8").read()
            t = re.sub(r'<a href="enso.html" class="enso-link">.*?</a>\s*', "", t, flags=re.S)
            open(dst, "w", encoding="utf-8").write(t)
        if f.endswith(".html") and "cps4" not in PUBLIC_SERIES:   # CPS4 を載せない場合だけ、HTML からも C3S（JMA）の出典欄・CPS4 の欄を取り除く
            t = open(dst, encoding="utf-8").read()
            t = re.sub(r'<span class="c3s">.*?</span>', "", t, flags=re.S)
            t = re.sub(r"<!--CPS4-->.*?<!--/CPS4-->", "", t, flags=re.S)
            open(dst, "w", encoding="utf-8").write(t)
    shutil.copytree(os.path.join(ROOT, "web", "guide_img"), os.path.join(site, "guide_img"))      # ガイドの実例の図
    files = sorted({fn for s in m["series"] for i in s["inits"]
                    for fn in list(i["files"].values()) + list(i.get("clim_files", {}).values()) + ([i["points"]] if i.get("points") else []) + ([i["dist"]] if i.get("dist") else []) + ([i["telecon"]] if i.get("telecon") else [])})
    for fn in files:
        shutil.copy(os.path.join(out_dir, fn), os.path.join(site, "output", fn))
    with open(os.path.join(site, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    enso_images = write_public_enso(site, out_dir) if PUBLISH_ENSO else []
    open(os.path.join(site, ".nojekyll"), "w").close()
    files = files + enso_images
    mb = sum(os.path.getsize(os.path.join(site, "output", fn)) for fn in files) / 1e6
    return m, files, mb


def check(site=SITE):
    """公開してはいけないものが入っていないか確かめる。問題の一覧を返す。"""
    bad = []
    for root, _, fs in os.walk(site):
        for f in fs:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, site)
            if f.endswith((".grib", ".grb", ".grb2", ".nc", ".npz", ".json")) and f not in ("manifest.json", "enso.json") and not f.startswith(("pt_", "dist_", "telecon_")):
                bad.append(rel)
    m = json.load(open(os.path.join(site, "manifest.json"), encoding="utf-8"))
    ep = os.path.join(site, "enso.json")
    if os.path.exists(ep) and "jma" in json.load(open(ep, encoding="utf-8")):
        bad.append("enso.json に気象庁の見通し(jma)が入っている（ローカルのみ）")
    if "cps4" not in PUBLIC_SERIES:                          # CPS4（JMA）を載せない場合: 図・json・HTML に混入していないか確かめる
        for root, _, fs in os.walk(site):
            for f in fs:
                if f.startswith(("cps4_", "pt_cps4", "dist_cps4", "clim_cps4", "enso_cps4", "telecon_cps4")):
                    bad.append(os.path.relpath(os.path.join(root, f), site))
        if any(x.get("id") == "cps4" for x in m["series"]):
            bad.append("manifest に cps4")
        for h in ("index.html", "board.html", "enso.html"):
            hp = os.path.join(site, h)
            if os.path.exists(hp) and re.search(r"JMA/MRI-CPS4|Copernicus", open(hp, encoding="utf-8").read()):
                bad.append(h + " に JMA/MRI-CPS4・Copernicus の記述が残っている")
    if "cps4" in PUBLIC_SERIES:                              # CPS4 を載せるなら、出典・免責の文言が HTML に残っているか確かめる
        for h in ("index.html", "board.html"):
            t = open(os.path.join(site, h), encoding="utf-8").read()
            if "Contains modified Copernicus Climate Change Service information" not in t:
                bad.append(h + " に Copernicus の出典文言が無い")
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
    print("公開前チェック: 元データ・json(manifest以外)・JMA/MRI-CPS4(C3S)に関するものは含まれていない")
    if a.publish:
        publish()
        print(f"{BRANCH} へ push しました")


if __name__ == "__main__":
    main()
