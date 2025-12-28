import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, Integer, Text, PrimaryKeyConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from src.config.settings import DB_CONNECTION_STRING

Base = declarative_base()

class PriceRaw(Base):
    __tablename__ = 'prices_raw'
    
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    adj_close = Column(Float)
    source = Column(String, nullable=False)  # stooq | yfinance
    ingested_at = Column(String, nullable=False)  # ISO timestamp
    
    __table_args__ = (
        PrimaryKeyConstraint('symbol', 'date', 'source'),
        Index('idx_prices_raw_date', 'date'),
    )

class PriceDaily(Base):
    __tablename__ = 'prices_daily'
    
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    adj_close = Column(Float)
    primary_source = Column(String, nullable=False)
    quality_flags = Column(Text, nullable=False)  # JSON string
    updated_at = Column(String, nullable=False)
    
    __table_args__ = (
        PrimaryKeyConstraint('symbol', 'date'),
        Index('idx_prices_daily_date', 'date'),
        Index('idx_prices_daily_symbol_date', 'symbol', 'date'),
    )

class Run(Base):
    __tablename__ = 'runs'
    
    run_id = Column(String, primary_key=True)
    asof_date = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    status = Column(String, nullable=False)
    config_hash = Column(String)
    code_version = Column(String)
    started_at = Column(String, nullable=False)
    ended_at = Column(String)
    error = Column(Text)
    
    __table_args__ = (
        Index('idx_runs_asof_mode', 'asof_date', 'mode'),
    )

class FeatureDaily(Base):
    __tablename__ = 'features_daily'
    
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)
    
    price_used = Column(Float, nullable=False)
    is_adjusted = Column(Integer, nullable=False) # 1 or 0
    
    pct_rank_5y = Column(Float)
    drawdown_3y = Column(Float)
    trend_hint = Column(Float)
    
    deepvalue_score_raw = Column(Float, nullable=False)
    deepvalue_score_smooth = Column(Float, nullable=False)
    
    data_quality_score = Column(Float)
    quality_flags = Column(Text, nullable=False) # JSON
    
    __table_args__ = (
        PrimaryKeyConstraint('symbol', 'date'),
        Index('idx_features_daily_date', 'date'),
    )

class LevelDaily(Base):
    __tablename__ = 'levels_daily'
    
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)
    
    s1 = Column(Float)
    s2 = Column(Float)
    s3 = Column(Float)
    r1 = Column(Float)
    r2 = Column(Float)
    r3 = Column(Float)
    
    s_meta = Column(Text, nullable=False) # JSON
    r_meta = Column(Text, nullable=False) # JSON
    quality_flags = Column(Text, nullable=False) # JSON
    
    __table_args__ = (
        PrimaryKeyConstraint('symbol', 'date'),
    )

class MarketStateDaily(Base):
    __tablename__ = 'market_state_daily'
    
    date = Column(String, primary_key=True)
    regime = Column(String, nullable=False) # risk_on | neutral | risk_off
    multiplier = Column(Float, nullable=False)
    inputs = Column(Text, nullable=False) # JSON
    
class RecommendationDaily(Base):
    __tablename__ = 'recommendations_daily'
    
    symbol = Column(String, nullable=False)
    date = Column(String, nullable=False)
    
    action = Column(String, nullable=False)
    plan_json = Column(Text, nullable=False)
    constraints_json = Column(Text, nullable=False)
    explain_json = Column(Text, nullable=False)
    llm_used = Column(Integer, nullable=False, default=0)
    
    __table_args__ = (
        PrimaryKeyConstraint('symbol', 'date'),
    )

class Report(Base):
    __tablename__ = 'reports'
    
    report_id = Column(String, primary_key=True)
    date = Column(String, nullable=False)
    type = Column(String, nullable=False) # daily | weekly
    content_md = Column(Text, nullable=False)
    meta_json = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)
    
    __table_args__ = (
        Index('idx_reports_date_type', 'date', 'type'),
    )

class LLMCache(Base):
    __tablename__ = 'llm_cache'
    
    cache_key = Column(String, primary_key=True)
    role = Column(String, nullable=False)
    input_json = Column(Text, nullable=False)
    output_json = Column(Text, nullable=False)
    validation_status = Column(String, nullable=False)
    created_at = Column(String, nullable=False)

class BacktestRun(Base):
    __tablename__ = 'backtest_runs'
    
    run_id = Column(String, primary_key=True)
    window_start = Column(String, nullable=False)
    window_end = Column(String, nullable=False)
    config_hash = Column(String)
    created_at = Column(String, nullable=False)
    meta_json = Column(Text) # JSON

class BacktestTrade(Base):
    __tablename__ = 'backtest_trades'
    
    trade_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    signal_date = Column(String, nullable=False) # Date trigger happened
    exec_date = Column(String, nullable=False)   # Date trade executed (next open)
    exec_price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    notional = Column(Float, nullable=False)
    tier = Column(String, nullable=False) # S1, S2, S3
    reason_json = Column(Text) # JSON
    
    __table_args__ = (
        Index('idx_bt_trades_run_symbol', 'run_id', 'symbol'),
    )

class BacktestSummary(Base):
    __tablename__ = 'backtest_summary'
    
    run_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    invested = Column(Float, nullable=False)
    buys = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    last_price = Column(Float, nullable=False)
    pnl_proxy = Column(Float, nullable=False)
    meta_json = Column(Text) # JSON
    
    __table_args__ = (
        PrimaryKeyConstraint('run_id', 'symbol'),
    )

# Database Interface
class DataStore:
    def __init__(self, connection_string=DB_CONNECTION_STRING):
        self.engine = create_engine(connection_string)
        self.Session = sessionmaker(bind=self.engine)
        
    def init_db(self):
        Base.metadata.create_all(self.engine)
        
    def get_session(self):
        return self.Session()
