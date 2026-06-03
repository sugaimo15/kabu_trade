import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics, calculate_trade_stats
from strategies.base import BaseStrategy
from strategies.technical import TechnicalStrategy


def make_dummy_data(n: int = 252, seed: int = 42) -> pd.DataFrame:
    """テスト用のダミー株価データを生成する。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-04", periods=n, freq="B")
    close = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    opens = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 1_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": opens, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


class AlwaysBuyStrategy(BaseStrategy):
    name = "always_buy"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=data.index, dtype=int)
        signals.iloc[0] = 1
        return signals


class AlternatStrategy(BaseStrategy):
    name = "alternate"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        signals = pd.Series(0, index=data.index, dtype=int)
        for i in range(0, len(signals), 20):
            signals.iloc[i] = 1
        for i in range(10, len(signals), 20):
            signals.iloc[i] = -1
        return signals


def test_engine_returns_equity_curve():
    data = make_dummy_data()
    engine = BacktestEngine()
    result = engine.run(AlwaysBuyStrategy(), data)
    assert len(result.equity_curve) == len(data)
    assert result.equity_curve.iloc[0] > 0


def test_engine_trade_count():
    data = make_dummy_data()
    engine = BacktestEngine()
    result = engine.run(AlternatStrategy(), data)
    assert result.trade_stats["total_trades"] > 0


def test_metrics_total_return():
    equity = pd.Series(
        [1_000_000, 1_050_000, 1_100_000],
        index=pd.date_range("2022-01-01", periods=3, freq="365D"),
    )
    m = calculate_metrics(equity)
    assert abs(m["total_return"] - 10.0) < 0.01


def test_metrics_max_drawdown():
    equity = pd.Series(
        [1_000_000, 1_200_000, 900_000, 1_100_000],
        index=pd.date_range("2022-01-01", periods=4, freq="90D"),
    )
    m = calculate_metrics(equity)
    assert m["max_drawdown"] < 0  # ドローダウンは負の値


def test_technical_strategy_generates_signals():
    data = make_dummy_data(n=300)
    strategy = TechnicalStrategy()
    signals = strategy.generate_signals(data)
    assert len(signals) == len(data)
    assert set(signals.unique()).issubset({-1, 0, 1})


def test_trade_stats_win_rate():
    trades = [
        {"entry_price": 1000, "exit_price": 1100, "side": 1},
        {"entry_price": 1000, "exit_price": 900, "side": 1},
        {"entry_price": 1000, "exit_price": 1050, "side": 1},
    ]
    stats = calculate_trade_stats(trades)
    assert stats["win_rate"] == pytest.approx(66.7, abs=0.1)
    assert stats["total_trades"] == 3
