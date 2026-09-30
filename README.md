# Stock Trend Scorer

## 概要
保有銘柄および市場全体の銘柄を対象に、価格トレンドをスコアリングするツール。

- 新規発掘: 上昇トレンドに入った銘柄をスクリーニング
- 保有監視: 保有銘柄のうち下落トレンドに入ったものを検知

## 対象市場
- 日本株
- 米国株

## セットアップ
```
git clone https://github.com/lite20020714-dev/stock-trend-scorer.git
cd stock-trend-scorer
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .
```

## 使い方
```
# 新規発掘(ランダム50件スキャン)
stock-trend-scorer scan --random 50 --universe jp

# 保有銘柄の追加
stock-trend-scorer add 7203

# 保有監視
stock-trend-scorer watch
```

GUI版(PySide6)も用意しています。
```
python gui_app.py
```

## データソース
- 米国株: yfinance
- 日本株: J-Quants API(または yfinance で代替可能かを検証)

## 保有銘柄の管理
- アプリ内で保有銘柄を独自に管理する(証券会社との連携なし)
- 保有数・金額は保持しない。銘柄コードのみを管理
- 保存先はローカルファイル(JSON or CSV)またはSQLiteの単一テーブル
- CLIコマンドで追加・削除を行う想定
  - 例: `add <銘柄コード>`, `remove <銘柄コード>`, `list`

## トレンド判定ロジック
以下の指標を組み合わせてスコアリングする。
- 移動平均線(SMA/EMA)のゴールデンクロス・デッドクロス
- 直近N日間の価格変化率
- RSI
- MACD
- 出来高の増減

## 移動平均の期間設定
- 新規発掘用: 短期5日 / 長期25日
- 保有監視用: 短期25日 / 長期75日

## スコアリング設計
- 各指標を -1 〜 +1 のスコアで評価
- 初期重みは全指標 1.0(均等配分)とし、過去データでのバックテスト結果を見ながら調整する
- 重み値は設定ファイル(JSON等)で外部化し、コード変更なしで調整可能にする
- 閾値に応じて以下に分類
  - 上昇トレンド候補
  - 下落トレンド警告(保有銘柄のみ対象)
  - 様子見

## 出力形式
- CLIに表示のみ(CSV/DB保存は将来的な拡張候補)

## バックテスト
`backtest` コマンドで、過去の各基準時点でのスコアとその後の値動きをCSVに出力する。対象銘柄の指定方法は `scan` と同じ(コード指定 / `--codes-file` / `--random N --universe jp|us`)。

```
stock-trend-scorer backtest AAPL MSFT 7203 --output bt.csv
stock-trend-scorer backtest --random 50 --universe us --output bt_us.csv
```

- 基準時点: 30ヶ月前〜6ヶ月前まで1ヶ月ごと(25時点。`--start-months` / `--end-months` / `--step-months` で変更可)
- 評価期間: 各基準時点から6ヶ月後まで(`--horizon-months`)
- スコアは基準時点までのデータ(直近1年分)のみで算出するため、先読みは発生しない
- `--mode watch` で保有監視モード、`--config` で重み・閾値JSONを指定可能
- CSVは1行 = 1銘柄 × 1基準時点。主な列:
  - `base_date`, `base_price`, `score`, `classification`
  - `max_price` / `min_price`(評価期間中の高値・安値)、`end_price`(評価期間最終日の終値)
  - `max_return_pct` / `min_return_pct` / `end_return_pct`(基準価格からの変化率 %)
  - `ind_*`(指標ごとのスコア。重みを変えた場合の再計算に使える)
- 実行後、スコア帯ごとの件数・平均/中央値リターン・勝率をCLIに表示する

### バックテスト結果
JP/US各100銘柄・25時点(計2,500サンプル)で6ヶ月後リターンとの相関を検証した結果、スコアと将来リターンの間に統計的に有意な相関は確認できませんでした(ピアソン相関係数 0.01〜0.03、スコア上位群/下位群のt検定でp値 > 0.3)。

評価期間を1〜6ヶ月の範囲で変えても改善は見られず、現在の5指標(移動平均クロス・価格変化率・RSI・MACD・出来高)による将来リターンの予測力は限定的という結論に至りました。本ツールは投資判断の根拠としてではなく、銘柄調査の入口(一次スクリーニング)としての利用を想定しています。

## 技術スタック
- Python
- pandas, numpy
- pandas-ta(テクニカル指標)
- yfinance / J-Quants API

## 検証方法
- 過去の既知の上昇/下落銘柄でスコアの妥当性を確認するテストを用意
- 重み付けをバックテストで調整できるよう、検証用スクリプトを別途用意する
- pytestで単体テストを書く
