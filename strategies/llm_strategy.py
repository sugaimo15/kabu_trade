import json
import time
from datetime import date

import anthropic
import pandas as pd
import yfinance as yf

from config.settings import ANTHROPIC_API_KEY
from strategies.base import BaseStrategy


class LLMStrategy(BaseStrategy):
    """
    Claude API を使用したニュース・財務情報のセンチメント分析戦略。

    yfinance から取得できる企業情報・ニュースを Claude に送り、
    買い/売り/ホールドの判断を得る。
    API コスト削減のため分析間隔を設定可能（デフォルト: 週1回更新）。
    """

    name = "llm"

    def __init__(
        self,
        update_interval_days: int = 7,
        model: str = "claude-haiku-4-5-20251001",
    ):
        self.update_interval_days = update_interval_days
        self.model = model
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._signal_cache: dict[str, tuple[date, int]] = {}

    def _fetch_company_context(self, ticker: str) -> str:
        """yfinance から企業情報・ニュースを取得してテキスト化する。"""
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info
        news = yf_ticker.news or []

        lines = []
        lines.append(f"企業名: {info.get('longName', ticker)}")
        lines.append(f"業種: {info.get('sector', '不明')} / {info.get('industry', '不明')}")
        lines.append(f"時価総額: {info.get('marketCap', '不明')}")
        lines.append(f"PER: {info.get('trailingPE', '不明')}")
        lines.append(f"PBR: {info.get('priceToBook', '不明')}")
        lines.append(f"ROE: {info.get('returnOnEquity', '不明')}")
        lines.append(f"営業利益率: {info.get('operatingMargins', '不明')}")
        lines.append(f"52週高値: {info.get('fiftyTwoWeekHigh', '不明')}")
        lines.append(f"52週安値: {info.get('fiftyTwoWeekLow', '不明')}")

        if news:
            lines.append("\n最新ニュース:")
            for item in news[:5]:
                title = item.get("title", "")
                if title:
                    lines.append(f"- {title}")

        return "\n".join(lines)

    def _analyze_with_claude(self, ticker: str, context: str) -> int:
        """Claude API でセンチント分析し、シグナル（1/-1/0）を返す。"""
        prompt = f"""以下は日本株 {ticker} の企業情報と最新ニュースです。

{context}

この情報を基に、今後1〜2週間の株価方向を判断してください。
以下の JSON 形式のみで回答してください（説明不要）:
{{"signal": 1, "reason": "短い理由"}}
- signal: 1（買い推奨）、-1（売り推奨）、0（ニュートラル）"""

        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            # JSON 部分を抽出
            start = text.find("{")
            end = text.rfind("}") + 1
            result = json.loads(text[start:end])
            signal = int(result.get("signal", 0))
            return signal if signal in (-1, 0, 1) else 0
        except Exception:
            return 0

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        注意: LLM 戦略はバックテストでの逐日分析には API コストがかかるため、
        update_interval_days ごとにシグナルを更新する形で動作する。
        """
        signals = pd.Series(0, index=data.index, dtype=int)

        # data の index から ticker を推定できないため、
        # このメソッドは analyze_ticker() を使う設計を想定。
        # バックテストエンジンから ticker を渡す場合は generate_signals_for() を使う。
        return signals

    def generate_signals_for(
        self, ticker: str, data: pd.DataFrame
    ) -> pd.Series:
        """
        ticker を指定してシグナルを生成する（バックテスト用）。
        API コスト削減のため update_interval_days ごとに1回だけ Claude を呼ぶ。
        """
        signals = pd.Series(0, index=data.index, dtype=int)
        current_signal = 0
        last_update: date | None = None

        for idx in data.index:
            current_date = idx.date() if hasattr(idx, "date") else idx

            should_update = (
                last_update is None
                or (current_date - last_update).days >= self.update_interval_days
            )

            if should_update:
                context = self._fetch_company_context(ticker)
                current_signal = self._analyze_with_claude(ticker, context)
                last_update = current_date
                time.sleep(0.5)  # レート制限対策

            signals[idx] = current_signal

        return signals
