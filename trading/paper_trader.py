# -*- coding: utf-8 -*-
"""
ペーパートレードモジュール

各戦略に仮想1万円を配分し、毎日シグナルに従って売買を実行する。
実際の証券会社APIは使わず、株価データだけを使った仮想取引。
"""
import sys
from datetime import date, timedelta

# Windows の PowerShell / コマンドプロンプトで日本語・記号を正しく表示する
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config.settings import ANTHROPIC_API_KEY
from data.fetcher import get_daily_ohlcv
from data.screener import screen_stocks
from strategies.ensemble import EnsembleStrategy
from strategies.ml_strategy import MLStrategy
from strategies.technical import TechnicalStrategy
from trading.portfolio import StrategyPortfolio

# 運用する戦略の一覧（4戦略 × 各1万円 = 合計4万円）
STRATEGIES = ["technical", "ml", "llm", "ensemble"]

# 各戦略の初期資金
INITIAL_CAPITAL = 10_000

# シグナル生成に使う過去データの日数
# MLStrategyが50サンプル以上必要なため365日以上を確保する
LOOKBACK_DAYS = 400


def _build_strategy(name: str):
    """戦略名から戦略インスタンスを生成する。"""
    if name == "technical":
        return TechnicalStrategy()
    if name == "ml":
        return MLStrategy()
    if name == "ensemble":
        return EnsembleStrategy(
            strategies=[(TechnicalStrategy(), 0.4), (MLStrategy(), 0.6)],
            threshold=0.3,
        )
    raise ValueError(f"未知の戦略: {name}")


def _get_latest_signal(strategy_name: str, ticker: str, data) -> int:
    """
    指定戦略・銘柄の最新シグナルを取得する。

    Parameters
    ----------
    strategy_name : str
    ticker        : str  証券コード（LLM戦略で使用）
    data          : DataFrame  前日までのOHLCV

    Returns
    -------
    int : 1=買い, -1=売り, 0=様子見
    """
    # LLM戦略は専用メソッドを使う
    if strategy_name == "llm":
        if not ANTHROPIC_API_KEY:
            return 0  # APIキー未設定時はスキップ
        try:
            from strategies.llm_strategy import LLMStrategy
            llm = LLMStrategy()
            # 直近1件だけ分析（APIコスト節約のため最終日のみ）
            context = llm._fetch_company_context(f"{ticker}.T")
            return llm._analyze_with_claude(ticker, context)
        except Exception:
            return 0

    strategy = _build_strategy(strategy_name)
    try:
        strategy.fit(data)
    except (NotImplementedError, AttributeError):
        pass

    signals = strategy.generate_signals(data)
    if signals.empty:
        return 0
    return int(signals.iloc[-1])


class PaperTrader:
    """
    全戦略のペーパートレードを一括管理するクラス。

    使い方:
        trader = PaperTrader()
        trader.run_daily()   # 毎日これを実行
        print(trader.get_summary())  # 損益確認
    """

    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.portfolios: dict[str, StrategyPortfolio] = {}
        self._load_all()

    def _load_all(self):
        for name in STRATEGIES:
            self.portfolios[name] = StrategyPortfolio.load(name, self.initial_capital)

    def _save_all(self):
        for portfolio in self.portfolios.values():
            portfolio.save()

    # ── 日次実行 ──────────────────────────────────

    def run_daily(self, top_n: int = 3) -> None:
        """
        毎日の取引処理を実行する。

        処理フロー:
          1. 銘柄スクリーニング（上位N銘柄を選定）
          2. 選定銘柄の株価データを取得
          3. 各戦略のシグナルを判定
          4. シグナルに従って仮想売買を実行
          5. ポートフォリオを保存
        """
        today = date.today().isoformat()
        end_date = date.today()
        start_date = end_date - timedelta(days=LOOKBACK_DAYS + 15)

        print(f"\n{'=' * 55}")
        print(f"  ペーパートレード実行: {today}")
        print(f"{'=' * 55}")

        # ── Step 1: 銘柄スクリーニング ──
        print("\n【Step 1】銘柄スクリーニング")
        selected = screen_stocks(top_n=top_n, budget_per_stock=self.initial_capital)
        if not selected:
            print("[!] スクリーニング結果が0件でした。スキップします。")
            return

        # 保有中の銘柄がスクリーニング結果に含まれていない場合は追加する
        selected_tickers = {s["ticker"] for s in selected}
        held_extra: list[dict] = []
        for portfolio in self.portfolios.values():
            for ticker, pos in portfolio.positions.items():
                if ticker not in selected_tickers:
                    held_extra.append({"ticker": ticker, "name": pos.name})
                    selected_tickers.add(ticker)
        if held_extra:
            names = ", ".join(f"{s['ticker']} {s['name']}" for s in held_extra)
            print(f"\n保有中のため追加: {names}")
            selected = selected + held_extra

        # ── Step 2: 株価データ取得 ──
        print("\n【Step 2】株価データ取得")
        stock_data: dict = {}
        current_prices: dict[str, float] = {}

        for stock in selected:
            ticker = stock["ticker"]
            try:
                df = get_daily_ohlcv(ticker, start_date, end_date)
                if not df.empty and len(df) >= 30:
                    stock_data[ticker] = df
                    current_prices[ticker] = float(df["Close"].iloc[-1])
                    print(f"  [OK] {ticker} {stock['name']}: "
                          f"{current_prices[ticker]:,.0f}円")
                else:
                    print(f"  [--] {ticker}: データ不足")
            except Exception as e:
                print(f"  [NG] {ticker}: 取得失敗 ({e})")

        if not stock_data:
            print("[!] 有効な株価データがありませんでした。")
            return

        # ── Step 3-4: シグナル判定 & 売買実行 ──
        print("\n【Step 3-4】シグナル判定 & 売買実行")

        for strategy_name, portfolio in self.portfolios.items():
            print(f"\n  >> [{strategy_name.upper()}]  "
                  f"現金: {portfolio.cash:,.0f}円  "
                  f"保有: {len(portfolio.positions)}銘柄")

            for stock in selected:
                ticker = stock["ticker"]
                name = stock["name"]

                if ticker not in stock_data:
                    continue

                price = current_prices[ticker]
                signal = _get_latest_signal(strategy_name, ticker, stock_data[ticker])
                signal_label = {1: "[買い]", -1: "[売り]", 0: "[様子見]"}[signal]
                holding = ticker in portfolio.positions

                # 売りシグナル & 保有中 → 売却
                if signal == -1 and holding:
                    portfolio.sell(ticker, price, today)
                    trade = portfolio.trades[-1]
                    print(f"    [売] {signal_label} {ticker} {name}  "
                          f"売値: {price:,.0f}円  "
                          f"{int(trade.shares)}株  "
                          f"損益: {trade.pnl:+,.0f}円 ({trade.pnl_pct:+.1f}%)")

                # 買いシグナル & 未保有 & 現金あり → 購入
                elif signal == 1 and not holding:
                    if portfolio.cash < price:
                        # 1株も買えない
                        print(f"    [--] {signal_label} {ticker} {name}  "
                              f"(予算不足: 1株{price:,.0f}円 / 残{portfolio.cash:,.0f}円)")
                    else:
                        # 戦略ごとの1銘柄あたり上限（初期資金 ÷ top_n）
                        per_stock_limit = self.initial_capital / max(1, top_n)
                        # 上限か残現金の少ない方を使う。ただし最低1株は確保
                        invest = max(per_stock_limit, price)
                        invest = min(invest, portfolio.cash)
                        success = portfolio.buy(ticker, name, price, invest, today)
                        if success:
                            trade = portfolio.trades[-1]
                            print(f"    [買] {signal_label} {ticker} {name}  "
                                  f"買値: {price:,.0f}円  "
                                  f"{int(trade.shares)}株  "
                                  f"投資額: {trade.amount:,.0f}円")
                        else:
                            print(f"    [--] {signal_label} {ticker} {name}  "
                                  f"(購入スキップ)")

                else:
                    status = "保有中" if holding else "未保有"
                    print(f"    [ ] {signal_label} {ticker} {name}  ({status})")

        # ── Step 5: 保存 ──
        self._save_all()
        print("\n[完了] ポートフォリオを保存しました。")

    # ── デイトレード実行 ──────────────────────────

    def run_daytrade(self, top_n: int = 3) -> None:
        """
        デイトレード版の日次処理。

        処理フロー:
          1. 銘柄スクリーニング
          2. 各銘柄の本日 OHLCV を取得
          3. 前日までのデータでシグナルを生成（本日分は使わない）
          4. 買いシグナルが出た銘柄を「始値で買い・終値で売り」で仮想執行
          5. ポートフォリオを保存

        注意: yfinance のデータは当日の取引終了後（15:30以降）に確定します。
        """
        today = date.today()
        today_str = today.isoformat()
        end_date = today
        start_date = end_date - timedelta(days=LOOKBACK_DAYS + 15)

        print(f"\n{'=' * 55}")
        print(f"  デイトレード実行: {today_str}")
        print(f"{'=' * 55}")

        # ── Step 1: 銘柄スクリーニング ──
        print("\n【Step 1】銘柄スクリーニング")
        selected = screen_stocks(top_n=top_n, budget_per_stock=self.initial_capital)
        if not selected:
            print("[!] スクリーニング結果が0件でした。スキップします。")
            return

        # 保有中の銘柄がスクリーニング結果に含まれていない場合は追加する
        selected_tickers = {s["ticker"] for s in selected}
        held_extra: list[dict] = []
        for portfolio in self.portfolios.values():
            for ticker, pos in portfolio.positions.items():
                if ticker not in selected_tickers:
                    held_extra.append({"ticker": ticker, "name": pos.name})
                    selected_tickers.add(ticker)
        if held_extra:
            names = ", ".join(f"{s['ticker']} {s['name']}" for s in held_extra)
            print(f"\n保有中のため追加: {names}")
            selected = selected + held_extra

        # ── Step 2: 本日の株価データ取得 ──
        print("\n【Step 2】本日の株価データ取得")
        stock_data: dict = {}
        today_ohlcv: dict[str, dict] = {}

        for stock in selected:
            ticker = stock["ticker"]
            try:
                df = get_daily_ohlcv(ticker, start_date, end_date)
                if df.empty or len(df) < 30:
                    print(f"  [--] {ticker}: データ不足")
                    continue
                open_val  = float(df["Open"].iloc[-1])
                close_val = float(df["Close"].iloc[-1])
                # NaN（売買停止・データ未確定）はスキップ
                if open_val != open_val or close_val != close_val:
                    print(f"  [--] {ticker}: 本日データ未確定（市場閉場後に再実行してください）")
                    continue
                stock_data[ticker] = df
                today_ohlcv[ticker] = {"open": open_val, "close": close_val}
                change = (close_val / open_val - 1) * 100
                print(f"  [OK] {ticker} {stock['name']}  "
                      f"始値: {open_val:,.0f}円  "
                      f"終値: {close_val:,.0f}円  "
                      f"騰落: {change:+.2f}%")
            except Exception as e:
                print(f"  [NG] {ticker}: 取得失敗 ({e})")

        if not stock_data:
            print("[!] 有効な株価データがありませんでした。")
            return

        # ── Step 3-4: シグナル判定 & デイトレード実行 ──
        print("\n【Step 3-4】シグナル判定 & デイトレード実行")
        print(f"  ※ シグナルは前日終値までのデータで判定します")

        for strategy_name, portfolio in self.portfolios.items():
            print(f"\n  >> [{strategy_name.upper()}]  資金: {portfolio.cash:,.0f}円")

            day_pnl = 0.0

            for stock in selected:
                ticker = stock["ticker"]
                name = stock["name"]
                if ticker not in stock_data:
                    continue

                # 前日までのデータでシグナルを生成（本日分を除外）
                data_for_signal = stock_data[ticker].iloc[:-1]
                signal = _get_latest_signal(strategy_name, ticker, data_for_signal)
                signal_label = {1: "[買い]", -1: "[売り]", 0: "[様子見]"}[signal]

                open_price  = today_ohlcv[ticker]["open"]
                close_price = today_ohlcv[ticker]["close"]
                change_pct  = (close_price / open_price - 1) * 100

                if signal != 1:
                    # 売り・様子見はデイトレードしない
                    print(f"    [ ] {signal_label} {ticker} {name}  スキップ")
                    continue

                if portfolio.cash < open_price:
                    print(f"    [--] {signal_label} {ticker} {name}  "
                          f"(予算不足: 1株{open_price:,.0f}円 / 残{portfolio.cash:,.0f}円)")
                    continue

                # 購入株数: 1銘柄上限（初期資金 / top_n）の範囲内で最大株数
                per_stock = max(self.initial_capital / max(1, top_n), open_price)
                per_stock = min(per_stock, portfolio.cash)
                shares = max(1, int(per_stock / open_price))
                shares = min(shares, int(portfolio.cash / open_price))

                success = portfolio.daytrade(ticker, name, open_price,
                                             close_price, shares, today_str)
                if success:
                    trade = portfolio.trades[-1]
                    day_pnl += trade.pnl
                    result_mark = "[+]" if trade.pnl >= 0 else "[-]"
                    print(f"    {result_mark} {signal_label} {ticker} {name}  "
                          f"始値{open_price:,.0f}→終値{close_price:,.0f}円  "
                          f"{shares}株  "
                          f"損益: {trade.pnl:+,.0f}円 ({trade.pnl_pct:+.2f}%)")

            pnl_mark = "[+]" if day_pnl >= 0 else "[-]"
            print(f"  {pnl_mark} 本日損益: {day_pnl:+,.0f}円  "
                  f"残資金: {portfolio.cash:,.0f}円")

        # ── Step 5: 保存 ──
        self._save_all()
        print("\n[完了] ポートフォリオを保存しました。")

    # ── 損益サマリ ────────────────────────────────

    def get_summary(self) -> str:
        """全戦略の損益サマリ文字列を返す。"""
        # 保有銘柄の現在価格を取得
        all_tickers: set[str] = set()
        for portfolio in self.portfolios.values():
            all_tickers.update(portfolio.positions.keys())

        current_prices: dict[str, float] = {}
        if all_tickers:
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
            for ticker in all_tickers:
                try:
                    df = get_daily_ohlcv(ticker, start_date, end_date)
                    if not df.empty:
                        current_prices[ticker] = float(df["Close"].iloc[-1])
                except Exception:
                    pass

        lines = [
            "",
            f"{'=' * 55}",
            "  ペーパートレード 損益サマリ",
            f"{'=' * 55}",
        ]

        total_initial = 0.0
        total_current = 0.0

        for name, portfolio in self.portfolios.items():
            tv = portfolio.total_value(current_prices)
            pnl = portfolio.total_pnl(current_prices)
            pnl_pct = portfolio.total_pnl_pct(current_prices)
            total_initial += portfolio.initial_capital
            total_current += tv

            mark = "[+]" if pnl >= 0 else "[-]"
            note = ""
            if name == "llm" and not ANTHROPIC_API_KEY:
                note = "  ※APIキー未設定"
            lines.append(
                f"  {mark} [{name.upper():10s}]  "
                f"評価額: {tv:>8,.0f}円  "
                f"損益: {pnl:>+6,.0f}円 ({pnl_pct:>+5.1f}%){note}"
            )

            # 保有銘柄の詳細
            for ticker, pos in portfolio.positions.items():
                cp = current_prices.get(ticker, pos.entry_price)
                pos_pnl = pos.pnl(cp)
                lines.append(
                    f"       +-- {ticker} {pos.name}  "
                    f"{cp:,.0f}円  "
                    f"含み損益: {pos_pnl:+,.0f}円"
                )

        total_pnl = total_current - total_initial
        total_pnl_pct = (total_current / total_initial - 1) * 100 if total_initial > 0 else 0.0

        lines += [
            f"  {'-' * 51}",
            f"  {'合計':14}  評価額: {total_current:>8,.0f}円  "
            f"損益: {total_pnl:>+6,.0f}円 ({total_pnl_pct:>+5.1f}%)",
            f"{'=' * 55}",
        ]
        return "\n".join(lines)
