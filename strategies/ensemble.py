import pandas as pd

from strategies.base import BaseStrategy


class EnsembleStrategy(BaseStrategy):
    """
    複数戦略のシグナルを統合するアンサンブル戦略。

    各戦略は独立して動作し、重み付き投票でシグナルを決定する。
    戦略は任意の組み合わせで使用可能（全3つでなくてもよい）。
    """

    name = "ensemble"

    def __init__(
        self,
        strategies: list[tuple[BaseStrategy, float]],
        threshold: float = 0.3,
    ):
        """
        Parameters
        ----------
        strategies : list of (strategy, weight)
            使用する戦略とその重みのリスト
        threshold : float
            シグナル確定のしきい値（加重平均がこの値を超えたら買い/売り）
        """
        self._strategies = strategies
        self.threshold = threshold
        total = sum(w for _, w in strategies)
        self._weights = [w / total for _, w in strategies]

    def fit(self, data: pd.DataFrame) -> None:
        for strategy, _ in self._strategies:
            strategy.fit(data)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        all_signals = []
        for strategy, _ in self._strategies:
            sig = strategy.generate_signals(data)
            all_signals.append(sig)

        weighted_sum = sum(
            sig * w for sig, w in zip(all_signals, self._weights)
        )

        signals = pd.Series(0, index=data.index, dtype=int)
        signals[weighted_sum >= self.threshold] = 1
        signals[weighted_sum <= -self.threshold] = -1
        return signals
