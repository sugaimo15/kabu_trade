import os
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルートの .env を明示的に指定（文字コード問題を回避）
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, encoding="utf-8", override=True)

JQUANTS_API_KEY = os.environ.get("JQUANTS_API_KEY", "")
JQUANTS_MAIL = os.environ.get("JQUANTS_MAIL", "")
JQUANTS_PASSWORD = os.environ.get("JQUANTS_PASSWORD", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# 取引コスト設定（楽天証券 超割コース参考）
COMMISSION_RATE = 0.0  # 楽天証券は一定条件で無料
MIN_COMMISSION = 0
SLIPPAGE_RATE = 0.001  # 0.1%（大型株想定）

# バックテスト デフォルト設定
INITIAL_CAPITAL = 1_000_000  # 100万円
POSITION_SIZE_RATE = 0.1     # 1銘柄あたり資産の10%

# 東証取引時間 (JST)
MORNING_START = "09:00"
MORNING_END = "11:30"
AFTERNOON_START = "12:30"
AFTERNOON_END = "15:30"
