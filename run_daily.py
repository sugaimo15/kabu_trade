"""
ペーパートレード 日次実行スクリプト

【使い方】
  # 毎日の取引を実行（銘柄選定 → シグナル判定 → 仮想売買）
  py run_daily.py

  # スクリーニングする銘柄数を変更（デフォルト: 3）
  py run_daily.py --top-n 5

  # 損益サマリだけ確認する（取引は行わない）
  py run_daily.py --status

  # 取引履歴を表示する
  py run_daily.py --history

  # 保有銘柄一覧を表示する
  py run_daily.py --positions

【ペーパートレードの仕組み】
  - 各戦略に仮想の 10,000円 を配分
  - 毎日実行すると、当日の株価データを取得してシグナルを判定
  - 買いシグナル → 仮想購入、売りシグナル → 仮想売却
  - 結果は trading/data/ フォルダに保存される（実際の取引は発生しない）

【注意事項】
  - ML戦略は過学習気味なので参考程度に（実運用には過学習対策が必要）
  - 日本株市場の取引時間外でも実行できる（終値ベースで計算）
  - 実際のお金は動かない（ペーパートレード）
"""

import argparse
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from trading.paper_trader import PaperTrader
from trading.report import show_positions, show_trade_history


def main():
    parser = argparse.ArgumentParser(
        description="ペーパートレード 日次実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--daytrade", action="store_true",
        help="デイトレードモード（始値で買い・終値で売り、翌日持ち越しなし）",
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="スクリーニングで選定する銘柄数 (デフォルト: 3)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="損益サマリのみ表示（取引は実行しない）",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="取引履歴を表示",
    )
    parser.add_argument(
        "--positions", action="store_true",
        help="現在の保有銘柄を表示",
    )
    parser.add_argument(
        "--strategy",
        choices=["technical", "ml", "ensemble"],
        default=None,
        help="表示する戦略を絞り込む（--history / --positions 用）",
    )
    args = parser.parse_args()

    trader = PaperTrader(initial_capital=10_000)

    if args.status:
        # 損益サマリのみ表示
        print(trader.get_summary())

    elif args.history:
        # 取引履歴を表示
        show_trade_history(strategy_name=args.strategy)

    elif args.positions:
        # 保有銘柄を表示
        show_positions(strategy_name=args.strategy)

    else:
        # 毎日の取引を実行
        if args.daytrade:
            trader.run_daytrade(top_n=args.top_n)
        else:
            trader.run_daily(top_n=args.top_n)
        # 実行後に損益サマリを表示
        print(trader.get_summary())


if __name__ == "__main__":
    main()
