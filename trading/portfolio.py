"""
ポートフォリオ管理モジュール

各戦略の資金・保有銘柄・取引履歴を管理し、JSONファイルに永続化する。
"""
import json
import os
from dataclasses import dataclass, asdict
from datetime import date

PORTFOLIO_DIR = "trading/data"


@dataclass
class Position:
    """保有銘柄の情報"""
    ticker: str
    name: str
    shares: float          # 保有株数（端株OK）
    entry_price: float     # 平均取得単価
    entry_date: str        # 購入日 (YYYY-MM-DD)

    def current_value(self, current_price: float) -> float:
        """時価評価額"""
        return self.shares * current_price

    def pnl(self, current_price: float) -> float:
        """含み損益（円）"""
        return self.shares * (current_price - self.entry_price)

    def pnl_pct(self, current_price: float) -> float:
        """含み損益率（%）"""
        return (current_price / self.entry_price - 1) * 100


@dataclass
class Trade:
    """取引履歴の1件"""
    date: str
    ticker: str
    name: str
    action: str      # "BUY" or "SELL"
    shares: float
    price: float
    amount: float    # 取引金額（円）
    pnl: float = 0.0       # 実現損益（SELL時のみ）
    pnl_pct: float = 0.0   # 実現損益率（SELL時のみ）


class StrategyPortfolio:
    """
    1戦略分のポートフォリオ。

    - 初期資金: 10,000円
    - 保有銘柄・現金残高・取引履歴を管理
    - save()/load() でJSONファイルに永続化
    """

    def __init__(self, strategy_name: str, initial_capital: float = 10_000):
        self.strategy_name = strategy_name
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.created_at = date.today().isoformat()

    # ── 評価 ──────────────────────────────────────

    def total_value(self, prices: dict[str, float]) -> float:
        """現在の総資産（現金 + 保有株の時価）"""
        stock_value = sum(
            pos.current_value(prices.get(t, pos.entry_price))
            for t, pos in self.positions.items()
        )
        return self.cash + stock_value

    def total_pnl(self, prices: dict[str, float]) -> float:
        """総損益（円）"""
        return self.total_value(prices) - self.initial_capital

    def total_pnl_pct(self, prices: dict[str, float]) -> float:
        """総損益率（%）"""
        return (self.total_value(prices) / self.initial_capital - 1) * 100

    # ── 売買 ──────────────────────────────────────

    def buy(self, ticker: str, name: str, price: float,
            amount: float, today: str) -> bool:
        """
        株を購入する（1株単位 = かぶミニ想定）。

        Parameters
        ----------
        amount : float
            投資金額（円）。現金を超える場合は現金残高を上限とする。
            実際に使う金額は「整数株数 × 株価」になる。
        """
        amount = min(amount, self.cash)
        if amount <= 0 or price <= 0:
            return False

        # 1株単位で購入できる最大株数を計算（かぶミニ想定）
        shares = int(amount / price)
        if shares < 1:
            return False  # 1株も買えない場合はスキップ

        amount = shares * price  # 実際の支払い金額
        self.cash -= amount

        if ticker in self.positions:
            # 追加購入 → 平均取得単価を更新
            pos = self.positions[ticker]
            total_shares = pos.shares + shares
            avg_price = (pos.shares * pos.entry_price + shares * price) / total_shares
            pos.shares = total_shares
            pos.entry_price = avg_price
        else:
            self.positions[ticker] = Position(
                ticker=ticker,
                name=name,
                shares=shares,
                entry_price=price,
                entry_date=today,
            )

        self.trades.append(Trade(
            date=today,
            ticker=ticker,
            name=name,
            action="BUY",
            shares=shares,
            price=price,
            amount=amount,
        ))
        return True

    def daytrade(self, ticker: str, name: str,
                 open_price: float, close_price: float,
                 shares: int, today: str) -> bool:
        """
        デイトレード（当日始値で買い・終値で売り）を1トランザクションで記録する。

        Parameters
        ----------
        open_price  : 始値（買いの執行価格）
        close_price : 終値（売りの執行価格）
        shares      : 株数（1株単位）
        """
        if shares < 1:
            return False
        cost = shares * open_price
        if cost > self.cash:
            return False

        revenue = shares * close_price
        pnl = revenue - cost
        pnl_pct = (close_price / open_price - 1) * 100

        self.cash += pnl  # 元本は維持したまま損益だけ加算

        self.trades.append(Trade(
            date=today,
            ticker=ticker,
            name=name,
            action="DAYTRADE",
            shares=float(shares),
            price=open_price,
            amount=cost,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
        ))
        return True

    def sell(self, ticker: str, price: float, today: str) -> bool:
        """保有株をすべて売却する。"""
        if ticker not in self.positions:
            return False

        pos = self.positions[ticker]
        amount = pos.shares * price
        pnl = pos.pnl(price)
        pnl_pct = pos.pnl_pct(price)

        self.cash += amount
        self.trades.append(Trade(
            date=today,
            ticker=ticker,
            name=pos.name,
            action="SELL",
            shares=pos.shares,
            price=price,
            amount=amount,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
        ))
        del self.positions[ticker]
        return True

    # ── 永続化 ────────────────────────────────────

    def save(self):
        """ポートフォリオ状態をJSONファイルに保存する。"""
        os.makedirs(PORTFOLIO_DIR, exist_ok=True)
        path = os.path.join(PORTFOLIO_DIR, f"{self.strategy_name}_portfolio.json")

        data = {
            "strategy_name": self.strategy_name,
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "created_at": self.created_at,
            "positions": {t: asdict(p) for t, p in self.positions.items()},
            "trades": [asdict(tr) for tr in self.trades],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, strategy_name: str,
             initial_capital: float = 10_000) -> "StrategyPortfolio":
        """
        保存済みのポートフォリオを読み込む。
        ファイルが存在しない場合は新規作成。
        """
        path = os.path.join(PORTFOLIO_DIR, f"{strategy_name}_portfolio.json")

        if not os.path.exists(path):
            return cls(strategy_name, initial_capital)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        portfolio = cls(strategy_name, data["initial_capital"])
        portfolio.cash = data["cash"]
        portfolio.created_at = data.get("created_at", date.today().isoformat())

        for ticker, pos_data in data.get("positions", {}).items():
            portfolio.positions[ticker] = Position(**pos_data)

        for trade_data in data.get("trades", []):
            portfolio.trades.append(Trade(**trade_data))

        return portfolio
