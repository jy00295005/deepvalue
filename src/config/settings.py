import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "deepvalue.db"

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Universe
MAG7_SYMBOLS = ["AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOGL", "GOOG"]
MARKET_PROXY_SYMBOL = "QQQ"
UNIVERSE = MAG7_SYMBOLS + [MARKET_PROXY_SYMBOL]

# Data Configuration
HISTORY_MIN_YEARS = 6
REQUEST_TIMEOUT = 30  # seconds

# Feature Configuration
PCT_RANK_WINDOW_YEARS = 5
DRAWDOWN_WINDOW_YEARS = 3
SCORE_SMOOTH_DAYS = 7
TREND_SMA_DAYS = 200

# Levels Configuration
SWING_WINDOW_K = 7
CLUSTER_TOL_PCT = 0.01
MAX_LEVELS = 3

# Policy / Budget Configuration
BUDGET_PER_SYMBOL_USD = 500
LADDER_DEFAULT_WEIGHTS_PCT = {"S1": 15, "S2": 25, "S3": 35}
RESERVE_PCT = 25
BUFFER_PCT = 0.01

# Market Regime Multipliers
REGIME_MULTIPLIERS = {
    "risk_on": 1.0,
    "neutral": 0.9,
    "risk_off": 0.7
}

ACCUMULATE_SCORE_MIN = 60
CHEAP_THRESHOLD = 70

# Database Connection String
DB_CONNECTION_STRING = f"sqlite:///{DB_PATH}"
