import numpy as np
import pandas as pd


def calculate_metrics(equity_curve: pd.Series, risk_free_rate: float = 0.001) -> dict:
    """
    バックテストのパフォーマンス指標を計算する。

    Parameters
    ----------
    equity_curve : pd.Series
        index=date, values=資産額の時系列
    risk_free_rate : float
        年率リスクフリーレート（デフォルト: 0.1%、日本の短期金利相当）

    Returns
    -------
    dict
        各種パフォーマンス指標
    """
    if len(equity_curve) < 2:
        return {}

    returns = equity_curve.pct_change().dropna()
    total_days = (equity_curve.index[-1] - equity_curve.index[0]).days
    years = total_days / 365.25

    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess_returns = returns - daily_rf
    sharpe = (
        excess_returns.mean() / excess_returns.std() * np.sqrt(252)
        if excess_returns.std() > 0
        else 0.0
    )

    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    return {
        "total_return": round(total_return * 100, 2),
        "annual_return": round(annual_return * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_drawdown * 100, 2),
        "calmar_ratio": round(calmar, 3),
        "total_days": total_days,
    }


def calculate_trade_stats(trades: list[dict]) -> dict:
    """
    取引履歴からトレード統計を計算する。

    Parameters
    ----------
    trades : list of dict
        各 dict: {entry_date, exit_date, entry_price, exit_price, side}
    """
    if not trades:
        return {"total_trades": 0}

    pnls = []
    for t in trades:
        if t["side"] == 1:
            pnl_pct = (t["exit_price"] - t["entry_price"]) / t["entry_price"]
        else:
            pnl_pct = (t["entry_price"] - t["exit_price"]) / t["entry_price"]
        pnls.append(pnl_pct)

    pnls = np.array(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    win_rate = len(wins) / len(pnls) if pnls.size > 0 else 0.0
    avg_win = wins.mean() if wins.size > 0 else 0.0
    avg_loss = abs(losses.mean()) if losses.size > 0 else 0.0
    profit_factor = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf")

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win * 100, 2),
        "avg_loss_pct": round(avg_loss * 100, 2),
        "profit_factor": round(profit_factor, 2),
    }
