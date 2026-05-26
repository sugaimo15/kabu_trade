from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """全戦略の共通インターフェース。独立して単体実行可能。"""

    name: str = "base"

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        売買シグナルを生成する。

        Parameters
        ----------
        data : pd.DataFrame
            index=date, columns=[Open, High, Low, Close, Volume]

        Returns
        -------
        pd.Series
            index=date, values: 1=買い, -1=売り, 0=ホールド
        """

    def fit(self, data: pd.DataFrame) -> None:
        """学習が必要な戦略（ML/LLM）はこのメソッドをオーバーライドする。"""
