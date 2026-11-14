# NOTICE — データの出典・ライセンスと、図に表示する文言

このプロジェクトは、公開されている気象データを加工して図を作る。データ源ごとの条件と、図・画面・文書に表示する文言をここにまとめる。
**2026-11-14 時点で公開情報から整理したもので、法的助言ではない。** 「未確認」は実際に読めていない・確認できていない事項。公開（Phase 5）の前に、必ず「公開前チェックリスト」と「未確認事項」を見直すこと。

## データ源ごとの条件と表示文言

### 1. NOAA/NCEP CFSv2（AWS `noaa-cfs-pds`）
- 条件: 米政府のデータで自由に使える。NOAA の推奨・提携を示唆しないこと。
- このプロジェクトでの使い方: 月平均・日別（6時間毎）から2m気温・降水・Z500・海洋水温を取り出し、2.5° に補間し、偏差・三分位確率に加工。
- 図に表示する文言: **「NOAA/NCEP CFSv2 を加工して作成（NOAAの推奨を示すものではない）。」**（`charts.render` が既定で表示）

### 2. NCEP/NCAR 再解析（NOAA PSL）
- 条件: NOAA PSL のデータ。利用時に出典を示す（PSL の通例の謝辞）。
- 使い方: **観測の代わり**としての検証（`verify.py`）と、気象庁の平年との基準差の見積もり（`baseline_offset.py`）。図そのものには出さない。
- 文書・論文等に書く文言（PSL の通例。正確な文言は PSL のページで確認）:
  「NCEP Reanalysis data provided by the NOAA Physical Sciences Laboratory (PSL), Boulder, Colorado, USA, from their website at https://psl.noaa.gov」／Kalnay et al., 1996, Bull. Amer. Meteor. Soc.

### 2b. GPCP・ERSSTv5・NCEP/NCAR 日別/月平均（検証用の観測。2026-11-14 追加）
- 使い方: 降水・Z500・海面水温の観測照合（`verify_cps4.py`・`verify_cfs_vars.py`）。**図そのものには出さず**、図の下端に「観測（GPCPの降水 など）との照合」と書くだけ。
- 配信: NOAA PSL（`downloads.psl.noaa.gov`）。GPCP v2.3 月平均降水（Adler et al., 2018, Atmosphere）、NOAA ERSST v5（Huang et al., 2017, J. Climate）、NCEP/NCAR 再解析（Kalnay et al., 1996）。いずれも NOAA PSL の「データ提供元の謝辞」を文書・論文等に付ける（正確な表記は各データのページで確認）。
- 注意: 降水の週平均の観測には、NCEP/NCAR **再解析の降水（モデル由来で精度が低い）**を使っている。Z500 は CFS と同じ NCEP 系の再解析で、**週1の技能（ACC 0.95）は観測と予報が近い系統のため過大に出ている可能性がある**。

### 3. Copernicus C3S（ECMWF 運営）経由の JMA/MRI-CPS4
- 提供: Copernicus Climate Change Service (C3S) の `seasonal-monthly-single-levels`・`seasonal-monthly-pressure-levels`（`originating_centre=jma`・`system=4`）。データセット DOI: **10.24381/cds.68dd14c3**。
- ライセンス（CDS の表示）: **CC-BY** と **Additional licence to use non European contributions (rev. 1)**。データセットごとに CDS 画面で同意が必要（同意済み）。
- 追加ライセンスの要旨（公開ページの記載）: C3S 季節予報マルチシステムのデータは**制限なく利用・再配布できる**。公表物ではデータの**原典を適切に明記**する。**提供センター（JMA 等）はサービスの継続や内容の品質を保証せず、利用に伴う問題に責任を負わない**。
- 図に表示する文言（`cps4.py` が表示）:
  - 「Generated using Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.」（Copernicus の標準的な表示文言。年は取得・加工した年に更新する）
  - 「JMA/MRI-CPS4 は気象庁が C3S に提供したデータで、提供元は品質・継続性を保証せず責任を負わない（C3S追加ライセンス）。データセット DOI: 10.24381/cds.68dd14c3。」
  - 「JMA/MRI-CPS4（Copernicus C3S 経由）を加工して作成。気象庁・C3Sの推奨を示すものではない。」
- 注意: 気象庁が直接配信するデータではなく、C3S のライセンスの下で入手している。気象庁の公式の長期予報（高い/平年並/低い）とは定義も基準も違うので混同させない。

### 4. ECMWF オープンデータ（このプロジェクトでは未使用）
- 姉妹の `week_forecast_charts` で使用。CC BY 4.0 と ECMWF 利用規約。再配布・商用利用は**適切な出典表示**を条件に可能。CC BY 4.0 は**改変した旨の表示**を求める。
- このプロジェクトで使う場合は、ECMWF の利用規約で表示文言（copyright・出典・ライセンス・免責）を確認してから、図に反映する。

### 5. 気象庁の公式予報・監視速報（JMA MCP 経由）
- 使い方: 1か月予報などの結果を**参考として併記**（`compare_jma.py`・`reference/*.json`）。
- 表示: **出典リンクを付ける**（グローバル CLAUDE.md の出典リンク表に従う）。気象庁の予報を加工・要約したときは、その旨を示す。当プロジェクトの図は気象庁の公式予報ではないと明記する。

## 共通のルール
- 配信元の推奨・提携を示唆しない。
- **加工した旨**を図に表示する（偏差・確率・補間・縮小を行っている）。
- 気象庁の公式予報と混同される表示にしない。定義（基準期間・確率の意味）が違うことを図や文書に明記する。
- **元の GRIB・再解析ファイルは公開しない**（再配布が許諾上可能でも、条件の確認を不要にするため）。公開するのは図・コード・文書だけ。`data/`・`output/` は git 除外のまま。
- API キー・`~/.cdsapirc` は公開しない（`.gitignore` 済み）。
- 表示年（Copernicus の文言）・ライセンスの版（revision）は、取得し直す・公開するときに確認し、変わっていれば更新する。

## 公開前チェックリスト（Phase 5・図を公開サイトに載せる前）
1. 載せる図の下端に、上の文言が入っている（CFS 系・CPS4 系それぞれ）。
2. 公開サイトの画面にも出典欄を設け、この NOTICE の要点と、気象庁の公式予報ではない旨を表示する。
3. 元データ（GRIB・再解析）をアップロードしていない。
4. 未確認事項（下）のうち、公開に関わるものを解消した。

## 未確認事項（2026-11-14）
- **C3S 追加ライセンスの全文を読めていない**（本文が PDF で、自動取得では読めなかった）。要旨は公開ページの記載による。**派生物・商用利用・禁止事項の記載は確認できていない**（禁止とも許可とも明記を確認していない）。ユーザーが次のページの「Download PDF」で全文を確認すること:
  https://ewds.climate.copernicus.eu/licences/Additional-licence-to-use-non-European-contributions
- Copernicus の標準的な表示文言（上記）が、今回のライセンスの正式な表示要件かは未確認（慣例に従い付けている）。
- JMA から C3S への提供データの二次利用について不安が残る場合は、C3S のサポートへ「JMA/MRI-CPS4 から作った派生図（偏差・確率）を公開サイトに載せてよいか」と問い合わせるのが確実。

## 更新履歴
| 日付 | 内容 |
|---|---|
| 2026-11-14 | 新規作成。NOAA CFSv2・NCEP/NCAR 再解析・C3S（JMA CPS4）・ECMWF オープンデータ・気象庁予報の条件と表示文言を整理 |
