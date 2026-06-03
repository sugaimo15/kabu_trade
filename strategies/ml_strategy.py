import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from strategies.base import BaseStrategy
from strategies.technical import _calc_rsi, _calc_macd_hist


class MLStrategy(BaseStrategy):
    """
    XGBoost による機械学習戦略。

    特徴量: 過去の OHLCV + テクニカル指標
    ラベル: 翌日の終値が threshold% 以上上昇 → 1（買い）
            翌日の終値が threshold% 以上下落 → -1（売り）
            それ以外 → 0（ホールド、学習データからは除外）
    """

    name = "ml"

    def __init__(
        self,
        lookback: int = 20,
        threshold: float = 0.005,  # 0.5% 以上の変動のみシグナル対象
        n_splits: int = 5,
    ):
        self.lookback = lookback
        self.threshold = threshold
        self.n_splits = n_splits
        self.model = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="mlogloss",
            verbosity=0,
        )
        self.scaler = StandardScaler()
        self._fitted = False

    def _build_features(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        features = pd.DataFrame(index=df.index)

        # 価格変化率
        for n in [1, 3, 5, 10, self.lookback]:
            features[f"ret_{n}"] = close.pct_change(n)

        # ボラティリティ
        features["vol_5"] = close.pct_change().rolling(5).std()
        features["vol_20"] = close.pct_change().rolling(20).std()

        # 移動平均乖離率
        for n in [5, 10, 25]:
            features[f"ma_dev_{n}"] = (close / close.rolling(n).mean()) - 1

        # テクニカル指標
        features["rsi"] = _calc_rsi(close, 14)
        features["macd_hist"] = _calc_macd_hist(close)
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        features["bb_width"] = (bb_upper - bb_lower) / ma20
        features["bb_pos"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, float("nan"))

        # 出来高
        features["vol_ratio"] = volume / volume.rolling(20).mean()

        # 高値・安値レンジ
        features["hl_ratio"] = (high - low) / close

        return features

    def _build_labels(self, data: pd.DataFrame) -> pd.Series:
        future_ret = data["Close"].pct_change(1).shift(-1)
        labels = pd.Series(0, index=data.index, dtype=int)
        labels[future_ret > self.threshold] = 1
        labels[future_ret < -self.threshold] = -1
        return labels

    def fit(self, data: pd.DataFrame) -> None:
        features = self._build_features(data).dropna()
        labels = self._build_labels(data).loc[features.index].shift(0)

        # ラベルが確定している行のみ使用（最終行は未来不明）
        valid = features.index[:-1]
        X = features.loc[valid]
        y = labels.loc[valid]

        # ホールド(0)を除いて buy/sell のみ学習
        mask = y != 0
        X_train = X[mask]
        y_train = y[mask]

        if len(X_train) < 50:
            raise ValueError("学習データが不足しています（50サンプル以上必要）")

        X_scaled = self.scaler.fit_transform(X_train)
        # XGBoost は -1 を扱えないため 0/1 にマッピング（売り→0、買い→1）
        y_mapped = y_train.map({-1: 0, 1: 1}).astype(int)
        self.model.fit(X_scaled, y_mapped)
        self._fitted = True

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if not self._fitted:
            raise RuntimeError("generate_signals の前に fit() を呼び出してください")

        features = self._build_features(data)
        valid = features.dropna().index
        X = features.loc[valid]
        X_scaled = self.scaler.transform(X)
        preds_mapped = self.model.predict(X_scaled)
        # 0→-1（売り）、1→1（買い）に戻す
        label_map = {0: -1, 1: 1}
        preds = pd.Series(
            [label_map[p] for p in preds_mapped],
            index=valid,
            dtype=int,
        )

        signals = pd.Series(0, index=data.index, dtype=int)
        signals.loc[preds.index] = preds
        return signals
