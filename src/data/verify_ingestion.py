from src.data.store import DataStore, PriceRaw, PriceDaily
from sqlalchemy import func
import pandas as pd
from loguru import logger

def verify_data():
    store = DataStore()
    session = store.get_session()
    
    # 1. Check Raw Counts
    logger.info("--- Raw Data Stats ---")
    raw_counts = session.query(PriceRaw.source, func.count(PriceRaw.date)).group_by(PriceRaw.source).all()
    for source, count in raw_counts:
        logger.info(f"Source {source}: {count} rows")
        
    # 2. Check Daily Counts
    logger.info("--- Daily Data Stats ---")
    daily_count = session.query(func.count(PriceDaily.date)).scalar()
    logger.info(f"Total Daily Rows: {daily_count}")
    
    # 3. Check Primary Source Distribution
    source_dist = session.query(PriceDaily.primary_source, func.count(PriceDaily.date)).group_by(PriceDaily.primary_source).all()
    for source, count in source_dist:
        logger.info(f"Primary Source {source}: {count} rows")
        
    # 4. Check Adjusted Flags (using JSON check is hard in pure SQL without extensions, so we load sample)
    # Actually we can check non-null adj_close as a proxy if we set it that way
    adj_count = session.query(func.count(PriceDaily.date)).filter(PriceDaily.adj_close.isnot(None)).scalar()
    logger.info(f"Rows with Adjusted Close: {adj_count}")

    # 5. Sample Data for AAPL
    logger.info("--- Sample Data (AAPL) ---")
    aapl_rows = session.query(PriceDaily).filter(PriceDaily.symbol == 'AAPL').order_by(PriceDaily.date.desc()).limit(5).all()
    for row in aapl_rows:
        logger.info(f"{row.date} | Close: {row.close:.2f} | Adj: {row.adj_close} | Source: {row.primary_source} | Flags: {row.quality_flags}")

if __name__ == "__main__":
    verify_data()
