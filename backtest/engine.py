from dataclasses import dataclass, field

import pandas as pd

from backtest.metrics import calculate_metrics, calculate_trade_stats
from config.settings import (
    COMMISSION_RATE,
    INITIAL_CAPITAL,
    POSITION_SIZE_RATE,
    SLIPPAGE_RATE,
)
from strategies.base import BaseStrategy


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[dict]
    signals: pd.Series
    metrics: dict = field(default_factory=dict)
    trade_stats: dict = field(default_factory=dict)

    def __post_init__(self):
        self.metrics = calculate_metrics(self.equity_curve)
        self.trade_stats = calculate_trade_stats(self.trades)

    def summary(self) -> str:
        lines = [
            "=" * 40,
            "バックテスト結果サマリ",
            "=" * 40,
            f"総リターン:       {self.metrics.get('total_return', 0):>8.2f}%",
            f"年率リターン:     {self.metrics.get('annual_return', 0):>8.2f}%",
            f"シャープレシオ:   {self.metrics.get('sharpe_ratio', 0):>8.3f}",
            f"最大ドローダウン: {self.metrics.get('max_drawdown', 0):>8.2f}%",
            f"カルマーレシオ:   {self.metrics.get('calmar_ratio', 0):>8.3f}",
            "-" * 40,
            f"総取引数:         {self.trade_stats.get('total_trades', 0):>8}",
            f"勝率:             {self.trade_stats.get('win_rate', 0):>8.1f}%",
            f"平均利益:         {self.trade_stats.get('avg_win_pct', 0):>8.2f}%",
            f"平均損失:         {self.trade_stats.get('avg_loss_pct', 0):>8.2f}%",
            f"プロフィットファクタ: {self.trade_stats.get('profit_factor', 0):>5.2f}",
            "=" * 40,
        ]
        return "\n".join(lines)


class BacktestEngine:
    """
    ベクトル化処理ベースの高速バックテストエンジン。

    - デイトレードモード: 当日中にポジションをクローズ
    - スイングモード: シグナルが反転するまでポジションを保持
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        commission_rate: float = COMMISSION_RATE,
        slippage_rate: float = SLIPPAGE_RATE,
        position_size_rate: float = POSITION_SIZE_RATE,
        daytrade_mode: bool = False,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.position_size_rate = position_size_rate
        self.daytrade_mode = daytrade_mode

    def _apply_cost(self, price: float, is_buy: bool) -> float:
        direction = 1 if is_buy else -1
        return price * (1 + direction * (self.commission_rate + self.slippage_rate))

    def run(self, strategy: BaseStrategy, data: pd.DataFrame) -> BacktestResult:
        """
        バックテストを実行する。

        Parameters
        ----------
        strategy : BaseStrategy
            シグナルを生成する戦略（事前に fit() 済みであること）
        data : pd.DataFrame
            index=date, columns=[Open, High, Low, Close, Volume]

        Returns
        -------
        BacktestResult
        """
        signals = strategy.generate_signals(data)

        capital = self.initial_capital
        equity_list = []
        trades = []
        position = 0       # 現在のポジション: 0=なし, 1=ロング, -1=ショート
        entry_price = 0.0
        entry_date = None
        shares = 0

        for i, (idx, row) in enumerate(data.iterrows()):
            close = row["Close"]
            signal = signals.get(idx, 0)

            # デイトレードモード: ポジションをその日のクローズで強制決済
            if self.daytrade_mode and position != 0 and signal == 0:
                signal = -position

            # 決済判断: ポジションが反転シグナル
            if position != 0 and (
                (position == 1 and signal == -1)
                or (position == -1 and signal == 1)
                or (self.daytrade_mode and signal == -position)
            ):
                exit_price = self._apply_cost(close, is_buy=(position == -1))
                if position == 1:
                    pnl = (exit_price - entry_price) * shares
                else:
                    pnl = (entry_price - exit_price) * shares
                capital += pnl + shares * entry_price  # 元本返却 + 損益

                trades.append({
                    "entry_date": entry_date,
                    "exit_date": idx,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "side": position,
                    "pnl": pnl,
                })
                position = 0
                shares = 0

            # 新規エントリー
            if position == 0 and signal in (1, -1):
                invest = capital * self.position_size_rate
                entry_price = self._apply_cost(close, is_buy=(signal == 1))
                shares = invest / entry_price if entry_price > 0 else 0
                capital -= invest
                position = signal
                entry_date = idx

            equity_list.append(capital + shares * close)

        equity_curve = pd.Series(equity_list, index=data.index)
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            signals=signals,
        )
