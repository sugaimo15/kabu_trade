import sqlite3
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DB = Path(__file__).parent / "cache" / "market_data.db"


def _ensure_cache_db():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            ticker TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.commit()
    conn.close()


def _load_from_cache(ticker: str, start: date, end: date) -> pd.DataFrame:
    conn = sqlite3.connect(CACHE_DB)
    df = pd.read_sql_query(
        "SELECT * FROM ohlcv WHERE ticker=? AND date>=? AND date<=? ORDER BY date",
        conn,
        params=(ticker, start.isoformat(), end.isoformat()),
    )
    conn.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").drop(columns=["ticker"])
    df.columns = [c.capitalize() for c in df.columns]
    return df


def _save_to_cache(ticker: str, df: pd.DataFrame):
    if df.empty:
        return
    rows = df.reset_index()
    rows.columns = [c.lower() for c in rows.columns]
    rows["ticker"] = ticker
    rows = rows.rename(columns={"index": "date", "datetime": "date"})
    if "date" not in rows.columns and rows.index.name == "date":
        rows = rows.reset_index()
    rows["date"] = pd.to_datetime(rows["date"]).dt.strftime("%Y-%m-%d")
    conn = sqlite3.connect(CACHE_DB)
    rows[["ticker", "date", "open", "high", "low", "close", "volume"]].to_sql(
        "ohlcv", conn, if_exists="replace", index=False,
        method="replace" if False else None,
    )
    conn.execute("""
        INSERT OR REPLACE INTO ohlcv (ticker, date, open, high, low, close, volume)
        SELECT ticker, date, open, high, low, close, volume FROM ohlcv
    """)
    conn.commit()
    conn.close()


def _to_yf_ticker(code: str) -> str:
    """4桁の証券コードを yfinance 形式に変換（例: 7203 → 7203.T）"""
    code = str(code)
    if code.isdigit() and len(code) == 4:
        return f"{code}.T"
    return code


def get_daily_ohlcv(
    code: str,
    start: date,
    end: date,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    日次 OHLCV データを取得する。
    キャッシュが存在すればキャッシュを優先し、なければ yfinance から取得。

    Parameters
    ----------
    code : str
        証券コード（例: "7203" または "7203.T"）
    start : date
        取得開始日
    end : date
        取得終了日（含む）
    use_cache : bool
        キャッシュを使用するか

    Returns
    -------
    pd.DataFrame
        index=date, columns=[Open, High, Low, Close, Volume]
    """
    _ensure_cache_db()
    ticker = _to_yf_ticker(code)

    if use_cache:
        cached = _load_from_cache(ticker, start, end)
        if not cached.empty:
            first_cached = cached.index[0].date()
            last_cached = cached.index[-1].date()
            # 開始日と終了日の両方をカバーしているか確認する
            # 終了日は土日祝を考慮して5日のマージンを許容
            if (first_cached <= start + timedelta(days=10)
                    and last_cached >= end - timedelta(days=5)):
                return cached

    # yfinance から取得（end+1日を指定しないと end 当日が含まれない）
    end_fetch = end + timedelta(days=1)
    raw = yf.download(
        ticker,
        start=start.isoformat(),
        end=end_fetch.isoformat(),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        return pd.DataFrame()

    # yfinance 0.2+ は MultiIndex カラム ('Open', '7203.T') を返すためフラット化
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "date"
    df.index = pd.to_datetime(df.index)

    if use_cache:
        save_df = df.copy()
        save_df.columns = [c.lower() for c in save_df.columns]
        save_rows = save_df.reset_index()
        save_rows["ticker"] = ticker
        save_rows["date"] = save_rows["date"].dt.strftime("%Y-%m-%d")
        conn = sqlite3.connect(CACHE_DB)
        for _, row in save_rows.iterrows():
            conn.execute(
                "INSERT OR REPLACE INTO ohlcv VALUES (?,?,?,?,?,?,?)",
                (row["ticker"], row["date"], row["open"], row["high"],
                 row["low"], row["close"], row["volume"]),
            )
        conn.commit()
        conn.close()

    return df.loc[start.isoformat():end.isoformat()]


def get_stock_list_jp() -> list[str]:
    """主要な日本株ティッカーリストを返す（TOPIX 100 相当の一例）"""
    return [
        "7203",  # トヨタ自動車
        "6758",  # ソニーグループ
        "9984",  # ソフトバンクグループ
        "8306",  # 三菱UFJフィナンシャル
        "6861",  # キーエンス
        "4063",  # 信越化学工業
        "7741",  # HOYA
        "8035",  # 東京エレクトロン
        "6954",  # ファナック
        "9432",  # 日本電信電話
    ]
