from src.data.store import DataStore, FeatureDaily, LevelDaily, MarketStateDaily
from sqlalchemy import select, func
from loguru import logger
import json

def verify_compute():
    store = DataStore()
    session = store.get_session()
    
    # 1. Features
    logger.info("--- Features Stats ---")
    feat_count = session.query(func.count(FeatureDaily.date)).scalar()
    logger.info(f"Total Feature Rows: {feat_count}")
    
    # Sample AAPL
    aapl_feat = session.query(FeatureDaily).filter(FeatureDaily.symbol == 'AAPL').order_by(FeatureDaily.date.desc()).first()
    if aapl_feat:
        logger.info(f"AAPL Latest Feature ({aapl_feat.date}): Score={aapl_feat.deepvalue_score_smooth:.2f} | Rank={aapl_feat.pct_rank_5y:.2f} | DD={aapl_feat.drawdown_3y:.2f} | Trend={aapl_feat.trend_hint}")

    # 2. Levels
    logger.info("--- Levels Stats ---")
    level_count = session.query(func.count(LevelDaily.date)).scalar()
    logger.info(f"Total Level Rows: {level_count}")
    
    # Sample AAPL
    aapl_level = session.query(LevelDaily).filter(LevelDaily.symbol == 'AAPL').order_by(LevelDaily.date.desc()).first()
    if aapl_level:
        logger.info(f"AAPL Latest Levels ({aapl_level.date}): S1={aapl_level.s1} | S2={aapl_level.s2} | S3={aapl_level.s3} | R1={aapl_level.r1}")
        
    # 3. Market State
    logger.info("--- Market State Stats ---")
    state_count = session.query(func.count(MarketStateDaily.date)).scalar()
    logger.info(f"Total Market State Rows: {state_count}")
    
    # Sample Latest
    latest_state = session.query(MarketStateDaily).order_by(MarketStateDaily.date.desc()).first()
    if latest_state:
        logger.info(f"Latest Market State ({latest_state.date}): Regime={latest_state.regime} | Multiplier={latest_state.multiplier}")

if __name__ == "__main__":
    verify_compute()
