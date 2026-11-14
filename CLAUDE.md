# CLAUDE.md — long_range_charts

## 概要
1か月以上先の長期予報（1か月・3か月・暖候期/寒候期）の判断に使う図（平年偏差・三分位確率・SST・循環指標）を作る。
マニュアルは [long-range-charts.md](long-range-charts.md)、設計は [DESIGN.md](DESIGN.md)、図種は [CHARTS.md](CHARTS.md)、データ源は [DATA_SOURCES.md](DATA_SOURCES.md)、計画は [PLAN.md](PLAN.md)。
週間〜2週間（〜15日先）は `../week_forecast_charts`（旧名 week_to_season_charts から2026-11-14に名称変更済み。GitHubのリポジトリ名・公開サイトも新名）で扱う。**このプロジェクトでは扱わない。**

## 実行環境
- Python: `/opt/anaconda3/envs/met_env_310/bin/python`（pygrib・cartopy・metpy・scipy・xarray・netCDF4・pytest）。`python3` は別環境になるので使わない（brew更新で切り替わる事例あり）。
- コメント・UIは日本語。インデント: Python 4スペース、JS/HTML/CSS 2スペース。

## 守ること
- **week_forecast_charts・nwp_chart_web・tenkizu_web とは共通部品化しない**（必要ならコピーして調整。各リポジトリは単独クローンで動く自己完結を優先）。
- **気象庁（気象業務支援センター）の有料配信は使わない**（2026-11-14 ユーザー決定）。気象庁モデルのデータ購入を提案しない。無料で使えるデータ源（NOAA CFS、ECMWF の無償提供分、Copernicus C3S など）で進める。
- **偏差の基準は「モデル自身の気候値（ハインドキャスト）」を原則とする**。再解析の平年値を基準にすると、モデルのバイアスが偏差に混ざる。基準にした気候値の出典・期間を図に必ず明記する。
- **確率・偏差の図には、モデル名・メンバー数・初期値・対象期間・気候値の出典と期間を図の下端に表示**する。
- **断定表現を避ける**。長期予報は「期間平均の傾向」であり、個々の日の天気は読めない。気象庁の公式の長期予報（高い/平年並/低いの階級確率）と混同される表示にしない。定義が違うときは図に明記する。
- 気象庁の公式予報を併記するときは `mcp__jma__*`（`get_monthly_forecast`・`get_3month_forecast`・`get_6month_forecast`・`get_elnino_monitor`）を使い、グローバルの CLAUDE.md の出典リンク表に従って**出典リンクを付ける**。
- 配信元の利用条件（NOAA は自由利用・NOAA の推奨を示唆しない／ECMWF・C3S は CC BY 等）に従い、出典・加工した旨を表示する。
- API キー・アカウント情報（Copernicus CDS など）は `.env` や `~/.config/` に分け、リポジトリに書かない・チャットに貼らない。**キーの作成・入力はユーザーが行う**。
- `data/`（GRIB2等）・`output/`・`logs/` は git 除外。公開（GitHub Pages）する場合は容量（1GB目安）を先に見積もる。
- push は毎回ユーザー確認が必要。GitHub リポジトリの作成・公開もユーザー確認が必要。

## ドキュメント更新
変更したら [long-range-charts.md](long-range-charts.md) と `pc_docs/manuals/automation/long-range-charts.md` の**両方**を更新し、`pc_docs/README.md` の表も直す。
