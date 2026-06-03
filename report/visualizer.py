from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager

matplotlib.use("Agg")  # GUI なし環境でも動作

# 利用可能な日本語フォントを自動検出（Windows / Linux / Mac 対応）
_JP_FONT_CANDIDATES = [
    "Yu Gothic", "YuGothic",          # Windows 8.1+
    "Meiryo", "MS Gothic", "MS PGothic",  # Windows
    "Hiragino Sans", "Hiragino Kaku Gothic ProN",  # macOS
    "IPAGothic", "IPAPGothic",         # Linux
    "Noto Sans CJK JP",                # Linux / Google
]
_available_fonts = {f.name for f in font_manager.fontManager.ttflist}
_jp_fonts = [f for f in _JP_FONT_CANDIDATES if f in _available_fonts]
plt.rcParams["font.family"] = _jp_fonts + ["DejaVu Sans"] if _jp_fonts else ["DejaVu Sans"]


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
    has_jp = bool(_jp_fonts)
    ax1.scatter(buy_idx, price_data.loc[buy_idx, "Close"],
                marker="^", color="red", s=60,
                label="買い" if has_jp else "Buy", zorder=5)
    ax1.scatter(sell_idx, price_data.loc[sell_idx, "Close"],
                marker="v", color="blue", s=60,
                label="売り" if has_jp else "Sell", zorder=5)
    ax1.set_ylabel("株価 (円)" if has_jp else "Price (JPY)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.set_title(title)
    ax1.grid(True, alpha=0.3)

    # 2. エクイティカーブ
    ax2 = axes[1]
    ax2.plot(equity_curve, color="green", linewidth=1.2)
    ax2.set_ylabel("資産 (円)" if has_jp else "Equity (JPY)")
    ax2.grid(True, alpha=0.3)
    ax2.axhline(equity_curve.iloc[0], color="gray", linestyle="--", linewidth=0.8)

    # 3. ドローダウン
    ax3 = axes[2]
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max * 100
    ax3.fill_between(drawdown.index, drawdown, 0, color="red", alpha=0.4)
    ax3.set_ylabel("ドローダウン (%)" if has_jp else "Drawdown (%)")
    ax3.set_xlabel("日付" if has_jp else "Date")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"チャート保存: {out}")
