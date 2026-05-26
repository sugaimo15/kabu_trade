from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")  # GUI なし環境でも動作
plt.rcParams["font.family"] = ["DejaVu Sans", "IPAGothic", "Noto Sans CJK JP"]


def plot_result(
    equity_curve: pd.Series,
    signals: pd.Series,
    price_data: pd.DataFrame,
    title: str = "バックテスト結果",
    output_path: str = "backtest_result.png",
) -> None:
    """
    エクイティカーブ・ドローダウン・シグナルを描画して画像保存する。
    """
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # 1. 価格チャートとシグナル
    ax1 = axes[0]
    ax1.plot(price_data["Close"], label="Close", color="black", linewidth=0.8)
    buy_idx = signals[signals == 1].index
    sell_idx = signals[signals == -1].index
    ax1.scatter(buy_idx, price_data.loc[buy_idx, "Close"],
                marker="^", color="red", s=60, label="買い", zorder=5)
    ax1.scatter(sell_idx, price_data.loc[sell_idx, "Close"],
                marker="v", color="blue", s=60, label="売り", zorder=5)
    ax1.set_ylabel("株価 (円)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.set_title(title)
    ax1.grid(True, alpha=0.3)

    # 2. エクイティカーブ
    ax2 = axes[1]
    ax2.plot(equity_curve, color="green", linewidth=1.2)
    ax2.set_ylabel("資産 (円)")
    ax2.grid(True, alpha=0.3)
    ax2.axhline(equity_curve.iloc[0], color="gray", linestyle="--", linewidth=0.8)

    # 3. ドローダウン
    ax3 = axes[2]
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max * 100
    ax3.fill_between(drawdown.index, drawdown, 0, color="red", alpha=0.4)
    ax3.set_ylabel("ドローダウン (%)")
    ax3.set_xlabel("日付")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"チャート保存: {out}")
