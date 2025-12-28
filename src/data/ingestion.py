import pandas as pd
import pandas_datareader.data as web
import yfinance as yf
from datetime import datetime, timedelta
from loguru import logger
import json
import numpy as np
from sqlalchemy.dialects.sqlite import insert
from src.data.store import DataStore, PriceRaw, PriceDaily, Run
from src.config.settings import HISTORY_MIN_YEARS, REQUEST_TIMEOUT

class DataIngestion:
    def __init__(self, store: DataStore):
        self.store = store
        self.db = store.get_session()

    def fetch_stooq(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        try:
            # Stooq symbols often need tickers like 'AAPL.US', but pandas_datareader usually handles 'AAPL'
            # Let's try 'AAPL' first. If it fails or returns empty, we might need to adjust.
            # Stooq via pandas_datareader
            df = web.DataReader(symbol, 'stooq', start_date, end_date)
            if df.empty:
                logger.warning(f"Stooq returned empty data for {symbol}")
                return pd.DataFrame()
            
            # Stooq returns index as Date, descending order usually
            df = df.sort_index()
            df['source'] = 'stooq'
            df = df.reset_index()
            # Standardize columns
            df.columns = [c.lower() for c in df.columns]
            # Stooq columns: date, open, high, low, close, volume. No adj_close usually.
            if 'adj_close' not in df.columns:
                df['adj_close'] = np.nan
            
            return df
        except Exception as e:
            logger.error(f"Failed to fetch from Stooq for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_yfinance(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        try:
            # yfinance expects YYYY-MM-DD strings or datetime objects
            # Use auto_adjust=False to get 'Adj Close' explicitly
            df = yf.download(symbol, start=start_date, end=end_date, progress=False, timeout=REQUEST_TIMEOUT, auto_adjust=False)
            if df.empty:
                logger.warning(f"yfinance returned empty data for {symbol}")
                return pd.DataFrame()
            
            # Flatten multi-index columns if present (yfinance > 0.2.0 sometimes does this)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df = df.sort_index()
            df['source'] = 'yfinance'
            df = df.reset_index()
            # Standardize columns: 'Adj Close' -> 'adj_close'
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            
            return df
        except Exception as e:
            logger.error(f"Failed to fetch from yfinance for {symbol}: {e}")
            return pd.DataFrame()

    def save_raw(self, df: pd.DataFrame, symbol: str):
        if df.empty:
            return

        records = []
        ingested_at = datetime.utcnow().isoformat()
        
        for _, row in df.iterrows():
            # Ensure types
            date_str = row['date'].strftime('%Y-%m-%d')
            
            record = {
                'symbol': symbol,
                'date': date_str,
                'open': float(row['open']) if pd.notnull(row['open']) else None,
                'high': float(row['high']) if pd.notnull(row['high']) else None,
                'low': float(row['low']) if pd.notnull(row['low']) else None,
                'close': float(row['close']) if pd.notnull(row['close']) else None,
                'volume': float(row['volume']) if pd.notnull(row['volume']) else None,
                'adj_close': float(row['adj_close']) if 'adj_close' in row and pd.notnull(row['adj_close']) else None,
                'source': row['source'],
                'ingested_at': ingested_at
            }
            records.append(record)

        if not records:
            return

        stmt = insert(PriceRaw).values(records)
        # On conflict do nothing for raw data? Or replace?
        # Since it's raw ingestion log, maybe we just ignore duplicates if exactly same keys
        # But we want to capture history. The PK is (symbol, date, source). 
        # If we fetch the same day from same source again, we update it.
        stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'date', 'source'],
            set_={
                'open': stmt.excluded.open,
                'high': stmt.excluded.high,
                'low': stmt.excluded.low,
                'close': stmt.excluded.close,
                'volume': stmt.excluded.volume,
                'adj_close': stmt.excluded.adj_close,
                'ingested_at': stmt.excluded.ingested_at
            }
        )
        
        self.db.execute(stmt)
        self.db.commit()

    def process_daily(self, symbol: str, df_stooq: pd.DataFrame, df_yf: pd.DataFrame):
        # Merge logic to produce prices_daily
        # We need a unified date range
        dates_stooq = set(df_stooq['date']) if not df_stooq.empty else set()
        dates_yf = set(df_yf['date']) if not df_yf.empty else set()
        all_dates = sorted(list(dates_stooq.union(dates_yf)))
        
        df_stooq = df_stooq.set_index('date') if not df_stooq.empty else pd.DataFrame()
        df_yf = df_yf.set_index('date') if not df_yf.empty else pd.DataFrame()
        
        records = []
        updated_at = datetime.utcnow().isoformat()
        prev_close = None
        
        EXTREME_MOVE_THRESHOLD = 0.25

        def check_validity(row):
            if row is None:
                return False, "missing"
            # Basic checks
            if not (pd.notnull(row['close']) and row['close'] > 0 and 
                    pd.notnull(row['volume']) and row['volume'] >= 0):
                return False, "invalid_basic"
            # Logical checks
            if row['high'] < row['low']:
                return False, "high_lt_low"
            if row['high'] < max(row['open'], row['close']):
                 # strict check, sometimes data can be slightly off, but H < max(O,C) is definitely wrong
                return False, "high_lt_open_close"
            if row['low'] > min(row['open'], row['close']):
                return False, "low_gt_open_close"
            return True, "ok"

        for d in all_dates:
            date_str = d.strftime('%Y-%m-%d')
            
            # 1. Try Stooq
            row_stooq = df_stooq.loc[d] if d in df_stooq.index else None
            # 2. Try yfinance
            row_yf = df_yf.loc[d] if d in df_yf.index else None
            
            chosen_row = None
            primary_source = None
            fallback_used = False
            quality_flags = {
                'missing_fields': False,
                'extreme_move': False,
                'split_suspected': False,
                'fallback_used': False,
                'is_adjusted': False,
                'notes': ''
            }
            
            stooq_valid, stooq_reason = check_validity(row_stooq)
            yf_valid, yf_reason = check_validity(row_yf)
            
            # Selection Logic
            if stooq_valid:
                # Check for extreme move if we have history
                use_stooq = True
                if prev_close is not None:
                    ret_stooq = abs(row_stooq['close'] / prev_close - 1)
                    if ret_stooq > EXTREME_MOVE_THRESHOLD:
                        # Stooq has extreme move. Check if yfinance is better.
                        if yf_valid:
                            ret_yf = abs(row_yf['close'] / prev_close - 1)
                            if ret_yf < EXTREME_MOVE_THRESHOLD:
                                # yfinance is stable, prefer it
                                use_stooq = False
                                quality_flags['notes'] += f"Stooq extreme move ({ret_stooq:.2%}), fallback to YF ({ret_yf:.2%}). "
                            else:
                                # Both extreme. Stick to Stooq but flag it.
                                quality_flags['notes'] += f"Stooq extreme move ({ret_stooq:.2%}). "
                        else:
                             quality_flags['notes'] += f"Stooq extreme move ({ret_stooq:.2%}). "
                
                if use_stooq:
                    chosen_row = row_stooq
                    primary_source = 'stooq'
                else:
                    chosen_row = row_yf
                    primary_source = 'yfinance'
                    fallback_used = True
            
            elif yf_valid:
                # Stooq invalid, use yfinance
                chosen_row = row_yf
                primary_source = 'yfinance'
                fallback_used = True
                quality_flags['notes'] += f"Stooq invalid ({stooq_reason}), fallback to YF. "
            
            else:
                # Both missing or bad quality
                logger.warning(f"Data missing/bad for {symbol} on {date_str} (Stooq: {stooq_reason}, YF: {yf_reason})")
                quality_flags['missing_fields'] = True # effectively missing for usage
                # We can't persist a record without valid price/volume usually, or we skip it?
                # MVP1: Skip it to avoid pollution, but log it.
                continue
            
            # Final check for extreme move on chosen row (to set the flag)
            if prev_close is not None and chosen_row is not None:
                ret = abs(chosen_row['close'] / prev_close - 1)
                if ret > EXTREME_MOVE_THRESHOLD:
                    quality_flags['extreme_move'] = True
            
            quality_flags['fallback_used'] = fallback_used
            
            # Prepare record
            adj_close = chosen_row.get('adj_close', np.nan)
            close = chosen_row['close']
            
            # Update prev_close for next iteration
            prev_close = close

            # Determine is_adjusted
            if pd.notnull(adj_close):
                quality_flags['is_adjusted'] = True
            else:
                quality_flags['is_adjusted'] = False
                adj_close = None # Store as None if NaN
            
            record = {
                'symbol': symbol,
                'date': date_str,
                'open': float(chosen_row['open']),
                'high': float(chosen_row['high']),
                'low': float(chosen_row['low']),
                'close': float(close),
                'volume': float(chosen_row['volume']),
                'adj_close': float(adj_close) if adj_close is not None else None,
                'primary_source': primary_source,
                'quality_flags': json.dumps(quality_flags),
                'updated_at': updated_at
            }
            records.append(record)
            
        if not records:
            return

        stmt = insert(PriceDaily).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'date'],
            set_={
                'open': stmt.excluded.open,
                'high': stmt.excluded.high,
                'low': stmt.excluded.low,
                'close': stmt.excluded.close,
                'volume': stmt.excluded.volume,
                'adj_close': stmt.excluded.adj_close,
                'primary_source': stmt.excluded.primary_source,
                'quality_flags': stmt.excluded.quality_flags,
                'updated_at': stmt.excluded.updated_at
            }
        )
        self.db.execute(stmt)
        self.db.commit()

    def run_ingestion(self, symbols: list[str], years: int = HISTORY_MIN_YEARS):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365)
        
        logger.info(f"Starting ingestion for {len(symbols)} symbols from {start_date.date()} to {end_date.date()}")
        
        for symbol in symbols:
            logger.info(f"Processing {symbol}...")
            
            # Fetch
            df_stooq = self.fetch_stooq(symbol, start_date, end_date)
            df_yf = self.fetch_yfinance(symbol, start_date, end_date)
            
            logger.info(f"Fetched {len(df_stooq)} rows from Stooq, {len(df_yf)} rows from yfinance for {symbol}")
            
            # Save Raw
            self.save_raw(df_stooq, symbol)
            self.save_raw(df_yf, symbol)
            
            # Process & Save Daily
            self.process_daily(symbol, df_stooq, df_yf)
            
        logger.info("Ingestion complete.")

if __name__ == "__main__":
    from src.config.settings import UNIVERSE
    store = DataStore()
    store.init_db()
    ingestion = DataIngestion(store)
    ingestion.run_ingestion(UNIVERSE)
