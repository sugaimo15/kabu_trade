# kabu_trade — 自動株取引バックテストシステム

## プロジェクト概要

日本株（東証）を対象とした自動取引バックテストシステム。
デイトレード・スイングトレードの両方に対応し、4種類の戦略を独立して実行できる。

## ディレクトリ構成

```
kabu_trade/
├── main.py                    # エントリーポイント（CLI）
├── requirements.txt           # 依存パッケージ
├── .env.example               # 環境変数のテンプレート
├── config/
│   └── settings.py            # APIキー・取引コスト・初期設定
├── data/
│   ├── fetcher.py             # yfinance でOHLCV取得 + SQLiteキャッシュ
│   └── cache/market_data.db   # 取得済みデータのキャッシュ（自動生成）
├── backtest/
│   ├── engine.py              # バックテストエンジン（BacktestEngine, BacktestResult）
│   └── metrics.py             # パフォーマンス指標計算（シャープ・DD・勝率など）
├── strategies/
│   ├── base.py                # 基底クラス BaseStrategy（ABC）
│   ├── technical.py           # 戦略1: MA/RSI/MACDルールベース
│   ├── ml_strategy.py         # 戦略2: XGBoost機械学習
│   ├── llm_strategy.py        # 戦略3: Claude APIニュース感情分析
│   └── ensemble.py            # 戦略4: 重み付きアンサンブル
├── report/
│   └── visualizer.py          # チャート生成（価格+シグナル・エクイティ・DD）
├── tests/
│   └── test_engine.py         # pytestユニットテスト
└── output/                    # 生成チャートの保存先（自動生成）
```

## 環境セットアップ

```powershell
# 依存パッケージのインストール
py -m pip install -r requirements.txt

# 日本語フォントを使う場合（オプション）
py -m pip install japanize-matplotlib
# インストール後、report/visualizer.py の import 直後に追加:
# import japanize_matplotlib

# 環境変数の設定（LLM戦略を使う場合のみ必要）
# .env.example を .env にコピーしてAPIキーを記入
```

## 実行コマンド

```powershell
# デモ（ネット不要、ダミーデータ）
py main.py --demo

# テクニカル戦略（トヨタ 2022〜2023年）
py main.py --strategy technical --ticker 7203 --start 2022-01-01 --end 2023-12-31

# 機械学習戦略
py main.py --strategy ml --ticker 7203 --start 2022-01-01 --end 2023-12-31

# LLM戦略（ANTHROPIC_API_KEY が必要）
py main.py --strategy llm --ticker 7203 --start 2022-01-01 --end 2023-12-31

# アンサンブル戦略（テクニカル + ML）
py main.py --strategy ensemble --ticker 7203 --start 2022-01-01 --end 2023-12-31

# 全戦略を比較
py main.py --compare-all --ticker 7203 --start 2022-01-01 --end 2023-12-31

# デイトレードモード（当日決済）
py main.py --strategy technical --ticker 7203 --daytrade

# ユニットテスト
py -m pytest tests/ -v
```

## 主要な設定（config/settings.py）

| 設定項目 | デフォルト値 | 説明 |
|----------|------------|------|
| `INITIAL_CAPITAL` | 1,000,000円 | 初期資金 |
| `POSITION_SIZE_RATE` | 0.1（10%） | 1銘柄あたりの資産比率 |
| `COMMISSION_RATE` | 0.0（0%） | 手数料率 |
| `SLIPPAGE_RATE` | 0.001（0.1%） | スリッページ |

## 戦略の概要

### 戦略1: TechnicalStrategy（`strategies/technical.py`）
- ゴールデン/デッドクロス（短期MA 5日 × 長期MA 25日）
- RSIフィルター（買い: RSI < 70、売り: RSI > 30）
- MACDヒストグラム確認
- `fit()` 不要。`generate_signals(data)` のみで動作

### 戦略2: MLStrategy（`strategies/ml_strategy.py`）
- XGBoostで翌日の価格方向を予測
- 特徴量: 価格変化率・ボラティリティ・MA乖離率・RSI・MACD・BB・出来高比
- **必ず `fit(data)` を先に呼ぶこと**

### 戦略3: LLMStrategy（`strategies/llm_strategy.py`）
- Claude API（claude-haiku-4-5）でニュース・財務情報を分析
- `ANTHROPIC_API_KEY` の設定が必要
- `generate_signals()` ではなく `generate_signals_for(ticker, data)` を使う
- APIコスト削減のため `update_interval_days=7`（週1回更新）

### 戦略4: EnsembleStrategy（`strategies/ensemble.py`）
- 複数戦略を重み付き投票で統合
- デフォルト: `TechnicalStrategy(重み0.4) + MLStrategy(重み0.6)`
- `threshold=0.3`（加重平均がこの値を超えたらシグナル確定）

## データ取得（data/fetcher.py）

```python
from data.fetcher import get_daily_ohlcv
from datetime import date

df = get_daily_ohlcv("7203", date(2022, 1, 1), date(2023, 12, 31))
# → index=date, columns=[Open, High, Low, Close, Volume]
```

- 証券コード: 4桁の数字（例: `7203`）→ 内部で `7203.T` に変換
- yfinanceから取得後、SQLiteにキャッシュ（2回目以降は高速）
- **yfinance 0.2+ のMultiIndexカラム問題は修正済み**（`get_level_values(0)` でフラット化）

## バックテストエンジン（backtest/engine.py）

```python
from backtest.engine import BacktestEngine

engine = BacktestEngine(
    initial_capital=1_000_000,
    daytrade_mode=False,  # True でデイトレードモード
)
result = engine.run(strategy, data)

print(result.summary())      # テキストサマリ出力
result.equity_curve          # pd.Series（資産推移）
result.trades                # list[dict]（取引履歴）
result.metrics               # dict（シャープ・DD等）
result.trade_stats           # dict（勝率・PF等）
```

## 既知の問題・注意事項

1. **日本語フォント警告**: Windowsで `findfont: Font family 'IPAGothic' not found.` が大量出力される。
   - 解決策: `py -m pip install japanize-matplotlib` → `visualizer.py` に `import japanize_matplotlib` を追加

2. **LLM戦略のバックテスト制限**: `generate_signals()` は全日付に0を返す。
   バックテストで使うには `generate_signals_for(ticker, data)` を使い、`main.py` の `run_single()` を修正する必要がある。

3. **MLStrategyの過学習**: デモデータでは勝率94%と高すぎる結果が出るが、実データでは大幅に下がる。
   Walk-forward validationの実装が今後の課題。

## 今後の拡張候補

- [ ] Walk-forward validation（時系列クロスバリデーション）
- [ ] J-Quants API対応（東証公式データへの切り替え）
- [ ] 複数銘柄ポートフォリオのバックテスト
- [ ] ロスカット・トレーリングストップの実装
- [ ] Streamlitダッシュボード
- [ ] ペーパートレード（定期実行 + Slack通知）
