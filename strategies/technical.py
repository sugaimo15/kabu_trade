import pandas as pd

from strategies.base import BaseStrategy


def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _calc_macd_hist(close: pd.Series,
                    fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd - signal_line


class TechnicalStrategy(BaseStrategy):
    """
    テクニカル指標に基づくルールベース戦略。

    シグナル生成ロジック（全条件の AND）:
    - ゴールデンクロス: 短期MA が 長期MA を上抜け → 買い
    - デッドクロス:     短期MA が 長期MA を下抜け → 売り
    - RSI フィルター:   買い時は RSI < rsi_buy、売り時は RSI > rsi_sell
    - MACD 確認:        MACD ヒストグラムの符号で方向を確認
    """

    name = "technical"

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 25,
        rsi_period: int = 14,
        rsi_buy: float = 70,   # ゴールデンクロス時は RSI<70（過熱していなければ買い）
        rsi_sell: float = 30,  # デッドクロス時は RSI>30（売られすぎでなければ売り）
        use_macd: bool = True,
    ):
        self.short_window = short_window
        self.long_window = long_window
        self.rsi_period = rsi_period
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.use_macd = use_macd

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        df = data.copy()
        close = df["Close"]

        # 移動平均
        df["ma_short"] = close.rolling(self.short_window).mean()
        df["ma_long"] = close.rolling(self.long_window).mean()

        # ゴールデン/デッドクロス検出
        prev_diff = df["ma_short"].shift(1) - df["ma_long"].shift(1)
        curr_diff = df["ma_short"] - df["ma_long"]
        golden_cross = (prev_diff < 0) & (curr_diff >= 0)
        dead_cross = (prev_diff > 0) & (curr_diff <= 0)

        # RSI
        df["rsi"] = _calc_rsi(close, self.rsi_period)

        # MACD
        if self.use_macd:
            df["macd_hist"] = _calc_macd_hist(close)
        else:
            df["macd_hist"] = 1  # フィルターなし

        signals = pd.Series(0, index=df.index, dtype=int)

        buy_cond = (
            golden_cross
            & (df["rsi"] < self.rsi_buy)
            & (df["macd_hist"] > 0)
        )
        sell_cond = (
            dead_cross
            & (df["rsi"] > self.rsi_sell)
            & (df["macd_hist"] < 0)
        )

        signals[buy_cond] = 1
        signals[sell_cond] = -1

        return signals
