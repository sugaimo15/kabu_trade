"""
Google Sheets 損益レポーター

ポートフォリオJSONを読み込み、Google Sheetsに損益サマリと取引履歴を書き込む。

必要な環境変数:
  GOOGLE_CREDENTIALS : サービスアカウントのJSONキー（文字列）
  SPREADSHEET_ID     : 書き込み先スプレッドシートのID
"""
import json
import os
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PORTFOLIO_DIR = Path("trading/data")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_client() -> gspread.Client:
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS が設定されていません")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _load_portfolios() -> dict:
    portfolios = {}
    for path in sorted(PORTFOLIO_DIR.glob("*_portfolio.json")):
        name = path.stem.replace("_portfolio", "")
        with open(path, encoding="utf-8") as f:
            portfolios[name] = json.load(f)
    return portfolios


def _get_or_create_sheet(ss: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return ss.worksheet(title)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=title, rows=1000, cols=20)


def _update_summary(ss: gspread.Spreadsheet, portfolios: dict, now: str) -> None:
    ws = _get_or_create_sheet(ss, "損益サマリ")

    headers = ["戦略", "初期資金(円)", "評価額(円)", "損益(円)", "損益率(%)", "保有銘柄数", "更新日時"]
    rows = [headers]

    total_initial = 0.0
    total_value_all = 0.0

    for name, data in portfolios.items():
        initial = data["initial_capital"]
        cash = data["cash"]
        positions = data.get("positions", {})
        stock_value = sum(p["shares"] * p["entry_price"] for p in positions.values())
        total_value = cash + stock_value
        pnl = total_value - initial
        pnl_pct = round((total_value / initial - 1) * 100, 1) if initial > 0 else 0.0

        total_initial += initial
        total_value_all += total_value

        rows.append([
            name.upper(),
            int(initial),
            round(total_value),
            round(pnl),
            pnl_pct,
            len(positions),
            now,
        ])

    total_pnl = total_value_all - total_initial
    total_pnl_pct = round((total_value_all / total_initial - 1) * 100, 1) if total_initial > 0 else 0.0
    rows.append(["合計", int(total_initial), round(total_value_all),
                 round(total_pnl), total_pnl_pct, "", now])

    ws.clear()
    ws.update(rows, value_input_option="USER_ENTERED")


def _update_history(ss: gspread.Spreadsheet, portfolios: dict) -> None:
    ws = _get_or_create_sheet(ss, "取引履歴")

    headers = ["日付", "戦略", "銘柄コード", "銘柄名", "売買",
               "株数", "価格(円)", "金額(円)", "損益(円)", "損益率(%)"]
    rows = [headers]

    all_trades = []
    for name, data in portfolios.items():
        for trade in data.get("trades", []):
            all_trades.append({**trade, "strategy": name.upper()})

    all_trades.sort(key=lambda x: x["date"], reverse=True)

    for t in all_trades:
        rows.append([
            t["date"],
            t["strategy"],
            t["ticker"],
            t["name"],
            t["action"],
            int(t["shares"]),
            round(t["price"]),
            round(t["amount"]),
            round(t.get("pnl", 0)),
            round(t.get("pnl_pct", 0), 1),
        ])

    ws.clear()
    ws.update(rows, value_input_option="USER_ENTERED")


def update_sheets(spreadsheet_id: str) -> None:
    client = _get_client()
    ss = client.open_by_key(spreadsheet_id)
    portfolios = _load_portfolios()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    _update_summary(ss, portfolios, now)
    _update_history(ss, portfolios)
    print(f"Google Sheets を更新しました ({now})")


if __name__ == "__main__":
    sid = os.environ.get("SPREADSHEET_ID")
    if not sid:
        raise ValueError("SPREADSHEET_ID が設定されていません")
    update_sheets(sid)
