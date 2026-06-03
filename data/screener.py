"""
銘柄スクリーニングモジュール

東証主要銘柄の中から、以下の基準で自動選定する:
  - 出来高が十分（流動性）
  - 直近のモメンタムが高い（上昇トレンド）
  - ボラティリティが適度（リスク管理）
"""
from datetime import date, timedelta

from data.fetcher import get_daily_ohlcv

# 候補銘柄リスト（業種分散した日経225主要銘柄）
CANDIDATE_STOCKS: dict[str, str] = {
    # 自動車
    "7203": "トヨタ自動車",
    "7267": "ホンダ",
    "7201": "日産自動車",
    # 電機・精密
    "6758": "ソニーグループ",
    "6861": "キーエンス",
    "6954": "ファナック",
    "6902": "デンソー",
    "8035": "東京エレクトロン",
    "4063": "信越化学工業",
    # 通信・IT
    "9984": "ソフトバンクグループ",
    "9432": "NTT",
    "9433": "KDDI",
    # 金融
    "8306": "三菱UFJ",
    "8316": "三井住友FG",
    "8411": "みずほFG",
    # 製薬
    "4502": "武田薬品工業",
    "4568": "第一三共",
    # 小売・消費
    "3382": "セブン&アイHD",
    "8267": "イオン",
    # その他
    "6367": "ダイキン工業",
    "7974": "任天堂",
    "9022": "JR東海",
}


def screen_stocks(
    top_n: int = 5,
    min_avg_volume: int = 500_000,
    lookback_days: int = 30,
    budget_per_stock: float = 0,
) -> list[dict]:
    """
    候補銘柄をスクリーニングして上位N銘柄を返す。

    Parameters
    ----------
    top_n : int
        返す銘柄数
    min_avg_volume : int
        最低平均出来高（流動性フィルター）
    lookback_days : int
        評価に使う過去データの日数

    Returns
    -------
    list[dict]
        [{"ticker", "name", "score", "last_price",
          "avg_volume", "momentum_pct", "volatility_pct"}, ...]
        スコア降順で並んでいる
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days + 15)

    results: list[dict] = []
    print(f"銘柄スクリーニング中... ({len(CANDIDATE_STOCKS)} 銘柄を評価)")

    for ticker, name in CANDIDATE_STOCKS.items():
        try:
            df = get_daily_ohlcv(ticker, start_date, end_date)
            if df.empty or len(df) < 10:
                continue

            avg_volume = float(df["Volume"].mean())
            if avg_volume < min_avg_volume:
                continue

            # NaN を含む場合はスキップ（上場廃止・売買停止銘柄の除外）
            close_series = df["Close"].dropna()
            if len(close_series) < 10:
                continue
            last_price = float(close_series.iloc[-1])
            first_price = float(close_series.iloc[0])
            if last_price != last_price or first_price != first_price:  # NaN チェック
                continue

            # モメンタム: 期間全体のリターン（高いほど上昇トレンド）
            momentum = (last_price / first_price - 1) * 100

            # ボラティリティ: 日次リターンの標準偏差（年率換算）
            daily_returns = close_series.pct_change(fill_method=None).dropna()
            volatility = float(daily_returns.std()) * (252 ** 0.5) * 100

            # スコア = モメンタム ÷ ボラティリティ（リスク調整後モメンタム）
            score = momentum / volatility if volatility > 0 else 0.0
            if score != score:  # NaN チェック
                continue

            results.append({
                "ticker": ticker,
                "name": name,
                "score": round(score, 3),
                "last_price": round(float(df["Close"].iloc[-1]), 0),
                "avg_volume": int(avg_volume),
                "momentum_pct": round(momentum, 2),
                "volatility_pct": round(volatility, 2),
            })

        except Exception as e:
            print(f"  {ticker} ({name}): スキップ ({e})")
            continue

    # スコア降順でソート
    results.sort(key=lambda x: x["score"], reverse=True)
    selected = results[:top_n]

    print(f"\n選定銘柄 (上位 {top_n} 銘柄):")
    print(f"  {'コード':6}  {'銘柄名':18}  {'スコア':>7}  {'現在値':>8}  "
          f"{'騰落率':>8}  {'ボラ':>7}  {'1株予算':>8}")
    print(f"  {'-'*75}")
    for r in selected:
        if budget_per_stock > 0:
            affordable = "OK" if r["last_price"] <= budget_per_stock else "予算超過"
        else:
            affordable = "-"
        print(
            f"  {r['ticker']:6}  {r['name'][:18]:18}  "
            f"{r['score']:>7.3f}  "
            f"{r['last_price']:>8,.0f}円  "
            f"{r['momentum_pct']:>+7.1f}%  "
            f"{r['volatility_pct']:>6.1f}%  "
            f"{affordable:>8}"
        )

    return selected
