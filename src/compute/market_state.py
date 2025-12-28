import pandas as pd
import numpy as np
import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from loguru import logger

from src.data.store import DataStore, PriceDaily, MarketStateDaily
from src.config.settings import (
    MARKET_PROXY_SYMBOL,
    TREND_SMA_DAYS
)

# Multipliers (could move to settings if needed, but per doc they are here or config)
# Doc 02_config_spec.md says they are in config. Let's put them here or import.
# Since settings.py didn't strictly have them in the previous edit, I'll define defaults here 
# or add them to settings if I want to be strict.
# Let's add them to settings first for consistency.

class MarketStateEngine:
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
                'adj_close': r.adj_close
            })
            
        df = pd.DataFrame(data).set_index('date')
        return df

    def compute_regime(self):
        symbol = MARKET_PROXY_SYMBOL
        df = self.load_prices(symbol)
        
        if df.empty:
            logger.warning(f"No prices found for market proxy {symbol}")
            return

        # Canonical Price
        df['price_used'] = df['adj_close'].fillna(df['close'])
        
        # SMA 200
        df['sma_200'] = df['price_used'].rolling(window=TREND_SMA_DAYS, min_periods=TREND_SMA_DAYS).mean()
        
        # Slope: SMA200(t) - SMA200(t-20)
        # 20 trading days approx 1 month
        df['sma_200_slope'] = df['sma_200'].diff(periods=20)
        
        # Regime Logic
        # risk_on: close >= SMA200 and slope >= 0
        # risk_off: close < SMA200 and slope < 0
        # neutral: otherwise
        
        def determine_regime(row):
            if pd.isna(row['sma_200']) or pd.isna(row['sma_200_slope']):
                return 'neutral', 0.9 # Default to neutral if not enough history
            
            price = row['price_used']
            sma = row['sma_200']
            slope = row['sma_200_slope']
            
            if price >= sma and slope >= 0:
                return 'risk_on', 1.0
            elif price < sma and slope < 0:
                return 'risk_off', 0.7
            else:
                return 'neutral', 0.9

        results = df.apply(determine_regime, axis=1, result_type='expand')
        df['regime'] = results[0]
        df['multiplier'] = results[1]
        
        self.save_state(df)

    def save_state(self, df: pd.DataFrame):
        records = []
        for date, row in df.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            
            inputs = {
                'price': row['price_used'],
                'sma_200': row['sma_200'] if pd.notnull(row['sma_200']) else None,
                'slope': row['sma_200_slope'] if pd.notnull(row['sma_200_slope']) else None
            }
            
            record = {
                'date': date_str,
                'regime': row['regime'],
                'multiplier': float(row['multiplier']),
                'inputs': json.dumps(inputs)
            }
            records.append(record)
            
        if not records:
            return

        stmt = insert(MarketStateDaily).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=['date'],
            set_={
                'regime': stmt.excluded.regime,
                'multiplier': stmt.excluded.multiplier,
                'inputs': stmt.excluded.inputs
            }
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(f"Saved {len(records)} market state rows")

    def run(self):
        logger.info(f"Computing market state for {MARKET_PROXY_SYMBOL}")
        try:
            self.compute_regime()
        except Exception as e:
            logger.error(f"Error computing market state: {e}")

if __name__ == "__main__":
    store = DataStore()
    engine = MarketStateEngine(store)
    engine.run()
