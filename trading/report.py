# -*- coding: utf-8 -*-
"""
レポート表示モジュール

取引履歴・損益明細を表示する。
"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from trading.paper_trader import STRATEGIES
from trading.portfolio import StrategyPortfolio


def show_trade_history(strategy_name: str | None = None, limit: int = 20) -> None:
    """
    取引履歴を表示する。

    Parameters
    ----------
    strategy_name : str | None
        指定した場合はその戦略のみ表示。None の場合は全戦略。
    limit : int
        表示する直近の件数。
    """
    names = [strategy_name] if strategy_name else STRATEGIES

    for name in names:
        portfolio = StrategyPortfolio.load(name)

        print(f"\n{'=' * 70}")
        print(f"  [{name.upper()}] 取引履歴 (直近 {limit} 件)")
        print(f"{'=' * 70}")

        if not portfolio.trades:
            print("  まだ取引履歴がありません。")
            continue

        print(f"  {'日付':12}  {'コード':6}  {'銘柄名':16}  {'売買':4}  "
              f"{'価格':>10}  {'金額':>10}  {'損益':>10}")
        print(f"  {'-' * 65}")

        for t in portfolio.trades[-limit:]:
            pnl_str = f"{t.pnl:+,.0f}円" if t.action == "SELL" else "     -"
            if t.action == "BUY":
                action_mark = "[買] BUY     "
            elif t.action == "SELL":
                action_mark = "[売] SELL    "
            else:
                action_mark = "[日] DAYTRADE"
            print(
                f"  {t.date:12}  {t.ticker:6}  {t.name[:16]:16}  "
                f"{action_mark}  "
                f"{t.price:>10,.0f}  "
                f"{t.amount:>9,.0f}円  "
                f"{pnl_str:>10}"
            )

        # 実現損益の合計
        realized = sum(t.pnl for t in portfolio.trades if t.action == "SELL")
        print(f"  {'-' * 65}")
        print(f"  実現損益合計: {realized:+,.0f}円")


def show_positions(strategy_name: str | None = None) -> None:
    """現在の保有銘柄一覧を表示する。"""
    names = [strategy_name] if strategy_name else STRATEGIES

    for name in names:
        portfolio = StrategyPortfolio.load(name)

        print(f"\n  [{name.upper()}]  現金: {portfolio.cash:,.0f}円  "
              f"保有銘柄数: {len(portfolio.positions)}")

        if not portfolio.positions:
            print("    （保有銘柄なし）")
            continue

        print(f"    {'コード':6}  {'銘柄名':16}  {'取得単価':>10}  {'保有株数':>10}  {'取得日':12}")
        for ticker, pos in portfolio.positions.items():
            print(
                f"    {ticker:6}  {pos.name[:16]:16}  "
                f"{pos.entry_price:>10,.0f}円  "
                f"{pos.shares:>10.4f}株  "
                f"{pos.entry_date:12}"
            )
