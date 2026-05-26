"""
kabu_trade — 自動株取引バックテストシステム

使用例:
  python main.py --strategy technical --ticker 7203 --start 2022-01-01 --end 2023-12-31
  python main.py --strategy ml --ticker 7203 --start 2022-01-01 --end 2023-12-31
  python main.py --strategy ensemble --ticker 7203 --start 2022-01-01 --end 2023-12-31
  python main.py --compare-all --ticker 7203 --start 2022-01-01 --end 2023-12-31
  python main.py --demo  # ネットワーク不要のデモ実行
"""

import argparse
from datetime import date

import numpy as np
import pandas as pd

from backtest.engine import BacktestEngine
from data.fetcher import get_daily_ohlcv
from report.visualizer import plot_result
from strategies.ensemble import EnsembleStrategy
from strategies.ml_strategy import MLStrategy
from strategies.technical import TechnicalStrategy


def make_demo_data(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """デモ用のダミー株価データを生成する。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 2000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    opens = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": opens, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


def parse_args():
    p = argparse.ArgumentParser(description="株式バックテストシステム")
    p.add_argument("--strategy", choices=["technical", "ml", "llm", "ensemble"],
                   default="technical", help="使用する戦略")
    p.add_argument("--ticker", default="7203", help="証券コード（例: 7203）")
    p.add_argument("--start", default="2022-01-01", help="開始日 (YYYY-MM-DD)")
    p.add_argument("--end", default="2023-12-31", help="終了日 (YYYY-MM-DD)")
    p.add_argument("--capital", type=float, default=1_000_000, help="初期資金（円）")
    p.add_argument("--daytrade", action="store_true", help="デイトレードモード（当日決済）")
    p.add_argument("--compare-all", action="store_true", help="全戦略を比較実行")
    p.add_argument("--no-chart", action="store_true", help="チャート出力をスキップ")
    p.add_argument("--demo", action="store_true", help="デモモード（ダミーデータで動作確認）")
    return p.parse_args()


def build_strategy(name: str):
    if name == "technical":
        return TechnicalStrategy()
    if name == "ml":
        return MLStrategy()
    if name == "llm":
        from strategies.llm_strategy import LLMStrategy
        return LLMStrategy()
    if name == "ensemble":
        tech = TechnicalStrategy()
        ml = MLStrategy()
        return EnsembleStrategy(strategies=[(tech, 0.4), (ml, 0.6)], threshold=0.3)
    raise ValueError(f"未知の戦略: {name}")


def run_single(strategy_name: str, data, engine: BacktestEngine, ticker: str,
               no_chart: bool):
    strategy = build_strategy(strategy_name)

    # 学習が必要な戦略は fit() を実行
    try:
        strategy.fit(data)
    except (NotImplementedError, AttributeError):
        pass

    result = engine.run(strategy, data)
    print(f"\n[{strategy_name.upper()}] {ticker}")
    print(result.summary())

    if not no_chart:
        plot_result(
            equity_curve=result.equity_curve,
            signals=result.signals,
            price_data=data,
            title=f"{ticker} — {strategy_name}",
            output_path=f"output/{ticker}_{strategy_name}.png",
        )
    return result


def main():
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.demo:
        data = make_demo_data()
        print(f"デモデータ生成完了: {len(data)} 日分")
    else:
        print(f"データ取得中: {args.ticker} ({args.start} 〜 {args.end})")
        data = get_daily_ohlcv(args.ticker, start, end)
        if data.empty:
            print(f"エラー: データを取得できませんでした ({args.ticker})")
            return
        print(f"取得完了: {len(data)} 日分")

    engine = BacktestEngine(
        initial_capital=args.capital,
        daytrade_mode=args.daytrade,
    )

    if args.compare_all:
        for name in ["technical", "ml"]:
            run_single(name, data, engine, args.ticker, args.no_chart)
    elif args.demo:
        print("=== デモモード（ダミーデータ）===")
        for name in ["technical", "ml", "ensemble"]:
            run_single(name, data, engine, "DEMO", args.no_chart)
    else:
        run_single(args.strategy, data, engine, args.ticker, args.no_chart)


if __name__ == "__main__":
    main()
