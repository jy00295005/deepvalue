import pandas as pd
import numpy as np
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from loguru import logger

from src.data.store import DataStore, PriceDaily, FeatureDaily
from src.config.settings import (
    PCT_RANK_WINDOW_YEARS,
    DRAWDOWN_WINDOW_YEARS,
    SCORE_SMOOTH_DAYS,
    TREND_SMA_DAYS
)

class FeatureEngine:
    def __init__(self, store: DataStore):
        self.store = store
        self.db = store.get_session()

    def load_prices(self, symbol: str) -> pd.DataFrame:
        stmt = select(PriceDaily).where(PriceDaily.symbol == symbol).order_by(PriceDaily.date)
        result = self.db.execute(stmt).scalars().all()
        
        if not result:
            return pd.DataFrame()
            
        data = []
        for r in result:
            data.append({
                'date': pd.to_datetime(r.date),
                'close': r.close,
                'adj_close': r.adj_close,
                'quality_flags': r.quality_flags
            })
            
        df = pd.DataFrame(data).set_index('date')
        return df

    def compute_for_symbol(self, symbol: str):
        df = self.load_prices(symbol)
        if df.empty:
            logger.warning(f"No prices found for {symbol}")
            return

        # Canonical Price selection
        # price_for_valuation = adj_close if not null else close
        df['price_used'] = df['adj_close'].fillna(df['close'])
        df['is_adjusted'] = df['adj_close'].notna().astype(int)

        # 1. Trend Hint (SMA 200)
        # We need 200 trading days
        sma_200 = df['price_used'].rolling(window=TREND_SMA_DAYS, min_periods=TREND_SMA_DAYS).mean()
        # trend_hint = 1 if price < SMA200 else 0 (Simple cheapness indicator)
        # Using a continuous version for smoother score: clamp((SMA - Price) / SMA, 0, 1) ? 
        # Doc says: "Trend hint = 1 if price < SMA200 else 0" or continuous. 
        # Let's stick to the doc example: 1 if cheap (below sma), 0 if expensive (above sma).
        # Actually, let's make it slightly continuous: 
        # If price is 10% below SMA, it's very cheap. If price is equal, it's neutral.
        # But to strictly follow the "deterministic" doc MVP: "Trend hint = 1 if price < SMA200 else 0"
        # Let's use the binary flag for now as base, maybe smoothed later.
        # Actually, let's use the continuous version from the design doc suggestion:
        # trend_hint = clamp((SMA200 - price)/SMA200, 0, 1)
        # If Price = 80, SMA = 100 => (100-80)/100 = 0.2. 
        # If Price = 120, SMA = 100 => negative => 0.
        # This gives a boost to score when price is significantly below trend.
        
        # However, to normalize this 0..1, we need to know how far below it can go. 
        # Let's just use binary for MVP1 stability as per doc "Example encoding: trend_hint = 1 if price < SMA200 else 0".
        df['trend_hint'] = (df['price_used'] < sma_200).astype(float)

        # 2. 5Y Percentile Rank
        # Window size in days approx 5 * 252 = 1260
        window_rank = PCT_RANK_WINDOW_YEARS * 252
        # Rolling rank. percent_rank returns 0..1
        # We want "Cheapness", so lower rank (lower price) is better?
        # pct_rank_5y in doc: "0..1 (lower is cheaper)". So simple percentile rank.
        df['pct_rank_5y'] = df['price_used'].rolling(window=window_rank, min_periods=252).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=True
        )

        # 3. 3Y Drawdown
        # Window size 3 * 252 = 756
        window_dd = DRAWDOWN_WINDOW_YEARS * 252
        rolling_max = df['price_used'].rolling(window=window_dd, min_periods=252).max()
        # Drawdown = 1 - (price / peak)
        # 0..1 (higher is deeper drawdown => cheaper)
        df['drawdown_3y'] = 1.0 - (df['price_used'] / rolling_max)
        
        # 4. DeepValue Score Raw
        # Weights:
        # - Rank (lower is better): contribution = (1 - rank) * W1
        # - Drawdown (higher is better): contribution = drawdown * W2
        # - Trend (1 if below SMA): contribution = trend * W3
        
        W1 = 0.5  # Rank is king
        W2 = 0.3  # Drawdown is queen
        W3 = 0.2  # Trend is knight
        
        # Handle NaNs (early history)
        # If features are NaN, score is NaN
        
        score_component_rank = (1.0 - df['pct_rank_5y']) * W1
        score_component_dd = df['drawdown_3y'] * W2
        score_component_trend = df['trend_hint'] * W3
        
        df['deepvalue_score_raw'] = (score_component_rank + score_component_dd + score_component_trend) * 100.0
        
        # Clip just in case
        df['deepvalue_score_raw'] = df['deepvalue_score_raw'].clip(0, 100)

        # 5. Smoothing
        df['deepvalue_score_smooth'] = df['deepvalue_score_raw'].rolling(window=SCORE_SMOOTH_DAYS, min_periods=1).mean()

        # Save to DB
        self.save_features(symbol, df)

    def save_features(self, symbol: str, df: pd.DataFrame):
        records = []
        for date, row in df.iterrows():
            if pd.isna(row['deepvalue_score_raw']):
                continue
                
            date_str = date.strftime('%Y-%m-%d')
            
            # Extract quality flags from source if needed, or create new ones
            # For now, just pass empty object or merge?
            # The schema says quality_flags is TEXT.
            # We can check if price used was adjusted.
            q_flags = {
                'is_adjusted': bool(row['is_adjusted']),
                'original_flags': row['quality_flags'] # Store upstream flags reference? Or just ignore for MVP
            }
            
            record = {
                'symbol': symbol,
                'date': date_str,
                'price_used': float(row['price_used']),
                'is_adjusted': int(row['is_adjusted']),
                'pct_rank_5y': float(row['pct_rank_5y']) if pd.notnull(row['pct_rank_5y']) else None,
                'drawdown_3y': float(row['drawdown_3y']) if pd.notnull(row['drawdown_3y']) else None,
                'trend_hint': float(row['trend_hint']) if pd.notnull(row['trend_hint']) else None,
                'deepvalue_score_raw': float(row['deepvalue_score_raw']),
                'deepvalue_score_smooth': float(row['deepvalue_score_smooth']),
                'data_quality_score': None, # MVP skip
                'quality_flags': json.dumps(q_flags)
            }
            records.append(record)
            
        if not records:
            return

        stmt = insert(FeatureDaily).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'date'],
            set_={
                'price_used': stmt.excluded.price_used,
                'is_adjusted': stmt.excluded.is_adjusted,
                'pct_rank_5y': stmt.excluded.pct_rank_5y,
                'drawdown_3y': stmt.excluded.drawdown_3y,
                'trend_hint': stmt.excluded.trend_hint,
                'deepvalue_score_raw': stmt.excluded.deepvalue_score_raw,
                'deepvalue_score_smooth': stmt.excluded.deepvalue_score_smooth,
                'quality_flags': stmt.excluded.quality_flags
            }
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Saved {len(records)} feature rows for {symbol}")

    def run(self, symbols: list[str]):
        logger.info(f"Computing features for {len(symbols)} symbols")
        for symbol in symbols:
            try:
                self.compute_for_symbol(symbol)
            except Exception as e:
                logger.error(f"Error computing features for {symbol}: {e}")

if __name__ == "__main__":
    from src.config.settings import UNIVERSE
    store = DataStore()
    engine = FeatureEngine(store)
    engine.run(UNIVERSE)
