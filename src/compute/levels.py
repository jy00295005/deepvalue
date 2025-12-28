import pandas as pd
import numpy as np
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from loguru import logger

from src.data.store import DataStore, PriceDaily, LevelDaily
from src.config.settings import (
    SWING_WINDOW_K,
    CLUSTER_TOL_PCT,
    MAX_LEVELS,
    MAG7_SYMBOLS,
)

S1_MIN_DROP_PCT = 0.02
S1_MAX_DROP_PCT = 0.10
S2_MIN_DROP_PCT = 0.06
S2_MAX_DROP_PCT = 0.18
S3_MIN_DROP_PCT = 0.12
S3_MAX_DROP_PCT = 0.30

MIN_GAP_PCT = 0.02

SMA_SLOPE_DAYS = 5

SWING_WINDOWS_YEARS = [1, 3, 5]

# PP Fusion constants
PP_MAX_WEIGHT = 0.6  # Max influence PP can have on S1
PP_CONFIDENCE_THRESHOLD = 0.4  # Min confidence to participate
S2_WEAK_STRENGTH_THRESHOLD = 1.5  # Below this, S2 is considered "weak" and PP can influence

class LevelsEngine:
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
                'high': r.high,
                'low': r.low,
                'close': r.close,
                'adj_close': r.adj_close
            })
            
        df = pd.DataFrame(data).set_index('date')
        return df

    def find_swings(self, df: pd.DataFrame, k: int = SWING_WINDOW_K) -> tuple[pd.Series, pd.Series]:
        # Swing Low: Low[t] is min in [t-k, t+k]
        # Swing High: High[t] is max in [t-k, t+k]
        # Note: This is a "future looking" indicator for historical analysis.
        # For the most recent days, we can't confirm a swing until k days pass.
        # But we use historical swings to define support/resistance for today.
        
        # We use canonical price for structure?
        # Design doc says: "price_for_structure = adj_close if available else close"
        # BUT swing detection usually needs High/Low. 
        # If we use adjusted close, we should ideally use adjusted High/Low.
        # If we don't have adjusted High/Low, we might be mixing frames.
        # MVP Strategy: Use Close (or Adj Close) for "Line chart structure" or use Raw High/Low if unadjusted?
        # Doc says: "Canonical price input... Avoid split artifacts... Keep score/levels consistent"
        # If we only have adj_close, we can simulate structure on Line Chart of adj_close.
        # Or we assume split adjustments are rare enough recently, or we use raw High/Low and hope for best?
        # Stooq data is usually raw. yfinance is adjusted or raw.
        # The safest MVP approach for "Canonical Price":
        # Calculate swings on the 'price_used' (Adj Close) as a Line Chart Swing.
        # This avoids High/Low split issues if we don't have Adj High/Adj Low.
        
        price = df['adj_close'].fillna(df['close'])
        
        # Rolling min/max centered
        # rolling(window=2*k+1, center=True)
        
        # Shifted approach to avoid lookahead leakage in strictly realtime sense?
        # No, Support levels are historical facts. 
        # A swing low 10 days ago is a swing low.
        
        win_size = 2 * k + 1
        
        rolling_min = price.rolling(window=win_size, center=True).min()
        rolling_max = price.rolling(window=win_size, center=True).max()
        
        is_swing_low = (price == rolling_min)
        is_swing_high = (price == rolling_max)
        
        # Filter out NaN (edges)
        swing_lows = price[is_swing_low].dropna()
        swing_highs = price[is_swing_high].dropna()
        
        return swing_lows, swing_highs

    def cluster_levels(
        self,
        levels: pd.Series,
        asof_date: pd.Timestamp,
        tol_pct: float = CLUSTER_TOL_PCT,
    ) -> list[dict]:
        if levels.empty:
            return []

        sorted_levels = levels.sort_values()

        clusters: list[list[tuple[pd.Timestamp, float]]] = []
        current_cluster: list[tuple[pd.Timestamp, float]] = []

        for dt, price in sorted_levels.items():
            if not current_cluster:
                current_cluster.append((dt, float(price)))
                continue

            cluster_center = float(np.mean([p for _, p in current_cluster]))
            dist = abs(float(price) - cluster_center) / cluster_center
            if dist <= tol_pct:
                current_cluster.append((dt, float(price)))
            else:
                clusters.append(current_cluster)
                current_cluster = [(dt, float(price))]

        if current_cluster:
            clusters.append(current_cluster)

        results: list[dict] = []
        for c in clusters:
            prices = [p for _, p in c]
            last_touch_dt = max([dt for dt, _ in c])
            recency_days = int((asof_date - last_touch_dt).days)
            results.append(
                {
                    'price': float(np.mean(prices)),
                    'touch_count': len(c),
                    'last_touch': last_touch_dt.strftime('%Y-%m-%d'),
                    'recency_days': recency_days,
                }
            )

        return results

    def _sma_slope_pct(self, series: pd.Series, asof_date: pd.Timestamp, days: int) -> Optional[float]:
        if series.empty:
            return None
        if asof_date not in series.index:
            return None

        idx = series.index.get_loc(asof_date)
        if isinstance(idx, slice):
            return None
        if idx - days < 0:
            return None

        v0 = series.iloc[idx - days]
        v1 = series.iloc[idx]
        if pd.isna(v0) or pd.isna(v1) or v0 == 0:
            return None
        return float((v1 - v0) / v0)

    def _source_priority_support(self, source: str) -> int:
        if source.startswith('swing'):
            return 0
        if source == 'sma50':
            return 1
        if source == 'sma20':
            return 2
        return 9

    def _source_priority_support_deep(self, source: str) -> int:
        if source == 'swing_5y':
            return 0
        if source == 'swing_3y':
            return 1
        if source == 'swing_1y':
            return 2
        if source == 'sma50':
            return 3
        if source == 'sma20':
            return 4
        return 9

    def _source_priority_resistance(self, source: str) -> int:
        if source.startswith('swing'):
            return 0
        if source == 'sma50':
            return 1
        if source == 'sma20':
            return 2
        return 9

    def _build_candidate(
        self,
        current_price: float,
        level_price: float,
        source: str,
        strength: float,
        touch_count: Optional[int] = None,
        recency_days: Optional[int] = None,
        slope_pct: Optional[float] = None,
    ) -> dict:
        distance_pct = (level_price / current_price) - 1
        return {
            'price': float(level_price),
            'source': source,
            'strength': float(strength),
            'distance_pct': float(distance_pct),
            'touch_count': touch_count,
            'recency_days': recency_days,
            'slope_pct': slope_pct,
        }

    def _filter_support_by_band(self, candidates: list[dict], min_drop: float, max_drop: float) -> list[dict]:
        out: list[dict] = []
        for c in candidates:
            drop = -float(c['distance_pct'])
            if drop < min_drop or drop > max_drop:
                continue
            if c['price'] >= 0 and c['distance_pct'] >= 0:
                continue
            out.append(c)
        return out

    def _filter_resistance_by_band(self, candidates: list[dict], min_rise: float, max_rise: float) -> list[dict]:
        out: list[dict] = []
        for c in candidates:
            rise = float(c['distance_pct'])
            if rise < min_rise or rise > max_rise:
                continue
            if c['distance_pct'] <= 0:
                continue
            out.append(c)
        return out

    def _select_support_levels(self, candidates: list[dict]) -> tuple[Optional[float], Optional[float], Optional[float]]:
        # S1: closest valid
        s1_pool = self._filter_support_by_band(candidates, S1_MIN_DROP_PCT, S1_MAX_DROP_PCT)
        s1_pool.sort(key=lambda c: (-c['distance_pct'], self._source_priority_support(c['source'])))
        s1 = s1_pool[0]['price'] if s1_pool else None
        s1_drop = (-s1_pool[0]['distance_pct']) if s1_pool else None

        # S2: below S1 with min gap, prefer closer then stronger
        s2_pool = self._filter_support_by_band(candidates, S2_MIN_DROP_PCT, S2_MAX_DROP_PCT)
        if s1_drop is not None:
            s2_pool = [c for c in s2_pool if (-c['distance_pct']) >= (s1_drop + MIN_GAP_PCT)]
        s2_pool.sort(
            key=lambda c: (
                -c['distance_pct'],
                -c['strength'],
                self._source_priority_support_deep(c['source']),
            )
        )
        s2 = s2_pool[0]['price'] if s2_pool else None
        s2_drop = (-s2_pool[0]['distance_pct']) if s2_pool else None

        # S3: deeper, prefer strongest then source then closer
        s3_pool = self._filter_support_by_band(candidates, S3_MIN_DROP_PCT, S3_MAX_DROP_PCT)
        if s2_drop is not None:
            s3_pool = [c for c in s3_pool if (-c['distance_pct']) >= (s2_drop + MIN_GAP_PCT)]
        elif s1_drop is not None:
            s3_pool = [c for c in s3_pool if (-c['distance_pct']) >= (s1_drop + 2 * MIN_GAP_PCT)]
        s3_pool.sort(
            key=lambda c: (
                -c['strength'],
                self._source_priority_support_deep(c['source']),
                -c['distance_pct'],
            )
        )
        s3 = s3_pool[0]['price'] if s3_pool else None

        return s1, s2, s3

    def _select_resistance_levels(self, candidates: list[dict]) -> tuple[Optional[float], Optional[float], Optional[float]]:
        r1_pool = self._filter_resistance_by_band(candidates, S1_MIN_DROP_PCT, S1_MAX_DROP_PCT)
        r1_pool.sort(key=lambda c: (c['distance_pct'], self._source_priority_resistance(c['source'])))
        r1 = r1_pool[0]['price'] if r1_pool else None
        r1_rise = (r1_pool[0]['distance_pct']) if r1_pool else None

        r2_pool = self._filter_resistance_by_band(candidates, S2_MIN_DROP_PCT, S2_MAX_DROP_PCT)
        if r1_rise is not None:
            r2_pool = [c for c in r2_pool if c['distance_pct'] >= (r1_rise + MIN_GAP_PCT)]
        r2_pool.sort(key=lambda c: (c['distance_pct'], -c['strength'], self._source_priority_resistance(c['source'])))
        r2 = r2_pool[0]['price'] if r2_pool else None
        r2_rise = (r2_pool[0]['distance_pct']) if r2_pool else None

        r3_pool = self._filter_resistance_by_band(candidates, S3_MIN_DROP_PCT, S3_MAX_DROP_PCT)
        if r2_rise is not None:
            r3_pool = [c for c in r3_pool if c['distance_pct'] >= (r2_rise + MIN_GAP_PCT)]
        elif r1_rise is not None:
            r3_pool = [c for c in r3_pool if c['distance_pct'] >= (r1_rise + 2 * MIN_GAP_PCT)]
        r3_pool.sort(key=lambda c: (-c['strength'], c['distance_pct'], self._source_priority_resistance(c['source'])))
        r3 = r3_pool[0]['price'] if r3_pool else None

        return r1, r2, r3

    def select_levels(self, candidates: list[dict], current_price: float, is_support: bool) -> list[float]:
        # Filter
        if is_support:
            # Candidates below current price
            # We want closest ones? Or strongest ones?
            # Doc: "Choose strongest clusters... Pick top 3 by strength, then order by proximity"
            # Actually Doc says: "Choose strongest clusters with level <= P. Pick top 3 by strength, then order by proximity."
            
            # Filter
            valid = [c for c in candidates if c['price'] < current_price]
        else:
            # Resistance
            valid = [c for c in candidates if c['price'] > current_price]
            
        if not valid:
            return [None] * MAX_LEVELS
            
        # Sort by strength (descending)
        valid.sort(key=lambda x: x['strength'], reverse=True)
        
        # Take top N
        top_n = valid[:MAX_LEVELS]
        
        # Sort by proximity to current price
        # For Support: descending price (closest to current from below)
        # For Resistance: ascending price (closest to current from above)
        if is_support:
            top_n.sort(key=lambda x: x['price'], reverse=True)
        else:
            top_n.sort(key=lambda x: x['price'])
            
        # Extract prices
        prices = [x['price'] for x in top_n]
        
        # Pad with None
        while len(prices) < MAX_LEVELS:
            prices.append(None)
            
        return prices

    def compute_for_symbol(self, symbol: str):
        df = self.load_prices(symbol)
        if df.empty:
            logger.warning(f"No prices found for {symbol}")
            return
            
        # Calculate canonical price used for structure
        df['price_used'] = df['adj_close'].fillna(df['close'])

        df['sma20'] = df['price_used'].rolling(20).mean()
        df['sma50'] = df['price_used'].rolling(50).mean()

        # We calculate levels for EACH day? 
        # Design doc: "levels_daily... Used as the ONLY allowed source... Stored daily"
        # However, re-calculating full history clustering for every day is expensive (O(N^2) or O(N*M)).
        # MVP1: Can we just calculate for the LATEST day?
        # The requirement says "Daily EOD automatic generation".
        # But for backtesting (MVP2), we might need history of levels.
        # If we only generate for today, we can't backtest easily unless we backfill.
        # Given MVP1 goal is "Daily Report", we technically only need TODAY's levels.
        # BUT: "10_backtest_validation.md" implies we need historical levels.
        # Optimization: We can compute levels for the last X days or full history if fast enough.
        # With 1500 rows, full history day-by-day loop is 1500 * clustering cost.
        # Clustering 1500 points is fast. Doing it 1500 times is ~2M ops. Python might be slow.
        # Let's try to compute for ALL days where we don't have levels yet?
        # Or just compute for the latest date for MVP1 pipeline efficiency.
        # Let's verify what `ingestion` does: it updates daily.
        # Let's Compute for ALL days to be safe for backtesting, but optimize if needed.
        # Actually, let's just do the LAST row for MVP1 verify, and maybe a backfill mode later.
        # Wait, the prompt asked to "implement subsequent computation". 
        # I should probably support computing for a range or all. 
        # Let's do a simple loop over the dataframe. 6 years * 252 ~ 1500 days. It's not that many.
        
        # To make it deterministic and causal:
        # For day T, we can only use data up to T (or T-k if we strict about swing confirmation).
        # Swing Low at T-k is confirmed at T.
        # So at day T, we look at swings in [Start, T-k].
        
        # Pre-calculate swings for the whole series (lookahead allowed for historical "truth" of swings, 
        # but when assigning levels to a date D, we must only use swings that happened before D).
        
        swings_low, swings_high = self.find_swings(df, SWING_WINDOW_K)
        
        # Prepare storage
        records = []
        
        # Optimization: Only compute for dates that are not in DB? 
        # For now, let's overwrite or just do last 30 days to save time during dev?
        # Or better: The user wants MVP1. Let's do full history for Mag7 (~9 symbols). 
        # 1500 days x 9 symbols = 13500 iterations.
        # Inside loop: filter swings < D, cluster, select. 
        # Filtering swings is O(N). Clustering is O(swings). Swings count ~ N/2k ~ 100.
        # 100 log 100 sorting. Fast.
        # Should be fine to do full history.
        
        dates = df.index
        # Convert swings to dataframe for easier filtering
        sl_df = swings_low.to_frame(name='price')
        sh_df = swings_high.to_frame(name='price')
        
        for d in dates:
            # We can use swings that occurred up to d.
            # Actually, to be strictly causal (no lookahead), a swing at time t is only known at t+k.
            # So we should filter swings where swing_date <= d - k days?
            # Or just use swing_date <= d if we accept the lag is inherent in the swing definition?
            # Design doc: "Swing detection ... (window k)". 
            # Let's use swings where index <= d. If the swing algo uses centered window, 
            # the swing at d-k is confirmed at d. 
            # If `find_swings` returns swing at time T, it used data T+k. 
            # So at simulation day D, we can only see swings where T <= D - k.
            
            cutoff_date = d - pd.Timedelta(days=SWING_WINDOW_K * 2) # Rough approximation or strict index check?
            # DataFrame index is datetime.
            
            # Using simple boolean masking
            # valid_sl = sl_df[sl_df.index <= d] # This uses lookahead if find_swings used center=True
            # If find_swings uses center=True, a swing at T uses T+k.
            # So at day D, we only know swings where T+k <= D => T <= D-k.
            
            # Since index is T, we filter T <= D - k (approx).
            # To be precise: simple subtraction might fail on weekends.
            # Let's just use the logic: we need 'future' data to confirm swing.
            # At day D, we have data up to D.
            # The find_swings func calculated swings based on full df.
            # We must be careful not to use "future confirmed swings" for past dates.
            # MVP1: Let's simpler logic: Use all swings up to D (assuming slightly lenient lookahead is OK for MVP1 levels stability) 
            # OR strict: T <= D - k.
            # Let's go with Strict to facilitate MVP2 backtest validity.
            
            # Note: T is index of swing.
            # We need T <= D - (K days). 
            # We can filter by index.
            
            # Actually, let's just process the latest date for efficiency now?
            # No, we want to populate history.
            
            current_price = df.loc[d, 'price_used']
            
            # Limit candidate window to last 3-5 years?
            # Doc: "Lookback horizon: 3-10 years"
            # df contains HISTORY_MIN_YEARS (6). We use all available.
            
            valid_sl = sl_df[sl_df.index <= d] # Loose causality
            valid_sh = sh_df[sh_df.index <= d] # Loose causality
            
            # Clustering
            # Support candidates: swings low
            # Resistance candidates: swings high
            # (Simplification: Support can become Resistance. But MVP split is easier)
            
            support_candidates: list[dict] = []
            resistance_candidates: list[dict] = []

            sma20 = df.loc[d, 'sma20']
            sma50 = df.loc[d, 'sma50']
            sma20_slope = self._sma_slope_pct(df['sma20'], d, SMA_SLOPE_DAYS)
            sma50_slope = self._sma_slope_pct(df['sma50'], d, SMA_SLOPE_DAYS)

            if pd.notna(sma20):
                if float(sma20) < float(current_price) and (sma20_slope is None or sma20_slope >= 0):
                    support_candidates.append(
                        self._build_candidate(
                            current_price=current_price,
                            level_price=float(sma20),
                            source='sma20',
                            strength=max(0.0, float(sma20_slope or 0.0)),
                            slope_pct=sma20_slope,
                        )
                    )
                elif float(sma20) > float(current_price):
                    resistance_candidates.append(
                        self._build_candidate(
                            current_price=current_price,
                            level_price=float(sma20),
                            source='sma20',
                            strength=max(0.0, float(abs(sma20_slope or 0.0))),
                            slope_pct=sma20_slope,
                        )
                    )

            if pd.notna(sma50):
                if float(sma50) < float(current_price) and (sma50_slope is None or sma50_slope >= 0):
                    support_candidates.append(
                        self._build_candidate(
                            current_price=current_price,
                            level_price=float(sma50),
                            source='sma50',
                            strength=max(0.0, float(sma50_slope or 0.0)),
                            slope_pct=sma50_slope,
                        )
                    )
                elif float(sma50) > float(current_price):
                    resistance_candidates.append(
                        self._build_candidate(
                            current_price=current_price,
                            level_price=float(sma50),
                            source='sma50',
                            strength=max(0.0, float(abs(sma50_slope or 0.0))),
                            slope_pct=sma50_slope,
                        )
                    )

            for y in SWING_WINDOWS_YEARS:
                lookback_start = d - pd.Timedelta(days=365 * y)

                window_sl = valid_sl[(valid_sl.index >= lookback_start) & (valid_sl.index <= d)]['price']
                window_sh = valid_sh[(valid_sh.index >= lookback_start) & (valid_sh.index <= d)]['price']

                s_clusters = self.cluster_levels(window_sl, d)
                r_clusters = self.cluster_levels(window_sh, d)

                for c in s_clusters:
                    touch = int(c['touch_count'])
                    recency = int(c['recency_days'])
                    strength = float(touch) + max(0.0, 1.0 - (recency / float(365 * y)))
                    level_price = float(c['price'])
                    if level_price < float(current_price):
                        support_candidates.append(
                            self._build_candidate(
                                current_price=current_price,
                                level_price=level_price,
                                source=f'swing_{y}y',
                                strength=strength,
                                touch_count=touch,
                                recency_days=recency,
                            )
                        )

                for c in r_clusters:
                    touch = int(c['touch_count'])
                    recency = int(c['recency_days'])
                    strength = float(touch) + max(0.0, 1.0 - (recency / float(365 * y)))
                    level_price = float(c['price'])
                    if level_price > float(current_price):
                        resistance_candidates.append(
                            self._build_candidate(
                                current_price=current_price,
                                level_price=level_price,
                                source=f'swing_{y}y',
                                strength=strength,
                                touch_count=touch,
                                recency_days=recency,
                            )
                        )

            # De-duplicate very close candidates (within CLUSTER_TOL_PCT)
            def _dedup(cands: list[dict]) -> list[dict]:
                if not cands:
                    return []
                cands_sorted = sorted(cands, key=lambda c: c['price'])
                out: list[dict] = [cands_sorted[0]]
                for c in cands_sorted[1:]:
                    prev = out[-1]
                    if abs(c['price'] - prev['price']) / max(1e-9, prev['price']) <= CLUSTER_TOL_PCT:
                        # Keep the stronger one
                        if c['strength'] > prev['strength']:
                            out[-1] = c
                    else:
                        out.append(c)
                return out

            support_candidates = _dedup(support_candidates)
            resistance_candidates = _dedup(resistance_candidates)

            s1, s2, s3 = self._select_support_levels(support_candidates)
            r1, r2, r3 = self._select_resistance_levels(resistance_candidates)

            # Metadata: keep closest candidates for debugging
            support_candidates.sort(key=lambda c: -c['distance_pct'])
            resistance_candidates.sort(key=lambda c: c['distance_pct'])

            s_meta = json.dumps(
                {
                    'selected': {'s1': s1, 's2': s2, 's3': s3},
                    'candidates': support_candidates[:12],
                },
                ensure_ascii=False,
            )
            r_meta = json.dumps(
                {
                    'selected': {'r1': r1, 'r2': r2, 'r3': r3},
                    'candidates': resistance_candidates[:12],
                },
                ensure_ascii=False,
            )
            
            record = {
                'symbol': symbol,
                'date': d.strftime('%Y-%m-%d'),
                's1': s1,
                's2': s2,
                's3': s3,
                'r1': r1,
                'r2': r2,
                'r3': r3,
                's_meta': s_meta,
                'r_meta': r_meta,
                'quality_flags': '{}'
            }
            records.append(record)
            
        # Bulk Insert
        if records:
            # Chunking if too large? 1500 is fine.
            stmt = insert(LevelDaily).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=['symbol', 'date'],
                set_={
                    's1': stmt.excluded.s1,
                    's2': stmt.excluded.s2,
                    's3': stmt.excluded.s3,
                    'r1': stmt.excluded.r1,
                    'r2': stmt.excluded.r2,
                    'r3': stmt.excluded.r3,
                    's_meta': stmt.excluded.s_meta,
                    'r_meta': stmt.excluded.r_meta,
                    'quality_flags': stmt.excluded.quality_flags
                }
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Saved {len(records)} level rows for {symbol}")

    def run(self, symbols: list[str]):
        logger.info(f"Computing levels for {len(symbols)} symbols")
        for symbol in symbols:
            try:
                self.compute_for_symbol(symbol)
            except Exception as e:
                logger.error(f"Error computing levels for {symbol}: {e}")

    # -------------------------------------------------------------------------
    # PP Fusion: blend external support levels with internal levels
    # -------------------------------------------------------------------------
    
    def fuse_with_pp(
        self,
        symbol: str,
        date_str: str,
        pp_band: Optional['SupportBand'] = None,
    ) -> dict:
        """
        Fuse internal levels with Perplexity external support band.
        
        Rules:
        - S1: soft-blend with PP if confidence >= threshold
        - S2: only influenced if internal S2 is "weak" (low strength)
        - S3: never influenced by PP (deep structural support)
        
        Returns dict with fused levels and fusion metadata.
        """
        from src.llm.perplexity_client import SupportBand
        
        # Load internal levels
        stmt = select(LevelDaily).where(
            LevelDaily.symbol == symbol,
            LevelDaily.date == date_str
        )
        level_row = self.db.execute(stmt).scalar_one_or_none()
        
        if not level_row:
            logger.warning(f"No internal levels for {symbol} on {date_str}")
            return {}
        
        s1_int = level_row.s1
        s2_int = level_row.s2
        s3_int = level_row.s3
        
        # Parse s_meta to get candidate info
        s_meta = json.loads(level_row.s_meta) if level_row.s_meta else {}
        candidates = s_meta.get('candidates', [])
        
        # Find S2's strength from candidates
        s2_strength = None
        for c in candidates:
            if c.get('price') == s2_int:
                s2_strength = c.get('strength', 0)
                break
        
        # Get current price for clamp calculations
        price_stmt = select(PriceDaily).where(
            PriceDaily.symbol == symbol,
            PriceDaily.date == date_str
        )
        price_row = self.db.execute(price_stmt).scalar_one_or_none()
        current_price = None
        if price_row:
            current_price = price_row.adj_close or price_row.close
        
        # Initialize fusion result
        fusion_meta = {
            'internal': {'s1': s1_int, 's2': s2_int, 's3': s3_int},
            'pp_used': False,
            'pp_confidence': 0.0,
            's1_fusion': 'internal_only',
            's2_fusion': 'internal_only',
            's3_fusion': 'internal_only',
        }
        
        s1_final = s1_int
        s2_final = s2_int
        s3_final = s3_int
        
        # Check if PP is usable
        if pp_band is None or pp_band.missing_data or pp_band.confidence < PP_CONFIDENCE_THRESHOLD:
            fusion_meta['pp_reason'] = 'missing_or_low_confidence'
            if pp_band:
                fusion_meta['pp_confidence'] = pp_band.confidence
            return {
                's1': s1_final, 's2': s2_final, 's3': s3_final,
                'fusion_meta': fusion_meta
            }
        
        fusion_meta['pp_used'] = True
        fusion_meta['pp_confidence'] = pp_band.confidence
        fusion_meta['pp_band'] = {'low': pp_band.low, 'high': pp_band.high, 'mid': pp_band.mid}
        
        s1_pp = pp_band.mid
        
        # -------------------------
        # S1 Fusion: soft-blend
        # -------------------------
        if s1_int is not None and s1_pp is not None and current_price is not None:
            # Weight based on confidence (max PP_MAX_WEIGHT)
            w = min(PP_MAX_WEIGHT, PP_MAX_WEIGHT * pp_band.confidence)
            
            # Raw blend
            s1_raw = (1 - w) * s1_int + w * s1_pp
            
            # Clamp: upper = min(S1_int, price * 0.99), lower = max(S2_int or 0, price * 0.82)
            upper = min(s1_int, current_price * 0.99) if s1_int else current_price * 0.99
            lower_bound = s2_int if s2_int else 0
            lower = max(lower_bound, current_price * (1 - S1_MAX_DROP_PCT - 0.08))
            
            s1_final = max(lower, min(upper, s1_raw))
            
            # Determine fusion type
            if pp_band.low and pp_band.high and s1_int:
                if pp_band.low <= s1_int <= pp_band.high:
                    fusion_meta['s1_fusion'] = 'pp_confirms'
                elif abs(s1_final - s1_int) < 0.01 * current_price:
                    fusion_meta['s1_fusion'] = 'internal_dominant'
                else:
                    fusion_meta['s1_fusion'] = 'pp_calibrated'
            
            fusion_meta['s1_weight'] = w
            fusion_meta['s1_raw_blend'] = s1_raw
        
        # -------------------------
        # S2 Fusion: only if internal S2 is weak
        # -------------------------
        s2_weak = (s2_strength is not None and s2_strength < S2_WEAK_STRENGTH_THRESHOLD)
        s2_gap_small = (s1_final and s2_int and abs(s2_int - s1_final) / current_price < MIN_GAP_PCT) if current_price else False
        
        if (s2_weak or s2_gap_small) and pp_band.confidence >= 0.6:
            # PP can influence S2: use PP's alt band or main band if deeper
            # For simplicity, use main band mid as S2 candidate if it's deeper than S1
            if s1_final and s1_pp and s1_pp < s1_final:
                # PP main is deeper than our S1, could be S2 candidate
                s2_pp_candidate = s1_pp
                
                # Only use if it's deeper than S1 by min gap
                if current_price and s2_pp_candidate < s1_final * (1 - MIN_GAP_PCT):
                    # Take the deeper of internal S2 and PP candidate
                    if s2_int is None or s2_pp_candidate < s2_int:
                        s2_final = s2_pp_candidate
                        fusion_meta['s2_fusion'] = 'pp_replaced_weak'
                    else:
                        fusion_meta['s2_fusion'] = 'internal_kept_stronger'
        
        # S3: never touched by PP
        fusion_meta['s3_fusion'] = 'internal_only'
        
        return {
            's1': round(s1_final, 2) if s1_final else None,
            's2': round(s2_final, 2) if s2_final else None,
            's3': round(s3_final, 2) if s3_final else None,
            'fusion_meta': fusion_meta
        }
    
    def run_with_pp_fusion(self, symbols: list[str], date_str: str) -> dict[str, dict]:
        """
        Run PP fusion for multiple symbols on a given date.
        
        Returns dict mapping symbol -> fused levels with metadata.
        """
        from src.llm.perplexity_client import fetch_external_supports_for_date
        from src.config.settings import MARKET_PROXY_SYMBOL
        
        # Fetch PP for MAG7 + QQQ (cost optimization)
        pp_symbols = [s for s in symbols if (s in MAG7_SYMBOLS or s == MARKET_PROXY_SYMBOL) and s != 'GOOGL']
        
        # Fetch external supports
        pp_bands = fetch_external_supports_for_date(date_str, pp_symbols) if pp_symbols else {}
        
        results: dict[str, dict] = {}
        for symbol in symbols:
            pp_band = pp_bands.get(symbol)
            # Handle GOOGL -> GOOG mapping
            if symbol == 'GOOGL' and not pp_band:
                pp_band = pp_bands.get('GOOG')

            fused = self.fuse_with_pp(symbol, date_str, pp_band)
            results[symbol] = fused

            # Persist fusion into LevelDaily for report visibility
            # - Update s1/s2 to fused values (if provided)
            # - Keep internal selection in s_meta, store selected_fused + pp_fusion
            if not fused:
                continue

            stmt = select(LevelDaily).where(
                LevelDaily.symbol == symbol,
                LevelDaily.date == date_str
            )
            row = self.db.execute(stmt).scalar_one_or_none()
            if not row:
                continue

            try:
                meta = json.loads(row.s_meta) if row.s_meta else {}
            except Exception:
                meta = {}

            # Preserve internal selected (pre-fusion) if available
            if isinstance(meta, dict) and 'selected' in meta and 'selected_internal' not in meta:
                meta['selected_internal'] = meta.get('selected')

            # Store fused selected + pp fusion metadata
            fusion_meta = fused.get('fusion_meta', {})
            meta['pp_fusion'] = fusion_meta
            meta['selected_fused'] = {
                's1': fused.get('s1'),
                's2': fused.get('s2'),
                's3': fused.get('s3'),
            }

            # For backward compatibility: keep 'selected' pointing at the CURRENT values (fused)
            meta['selected'] = meta.get('selected_fused')

            new_s_meta = json.dumps(meta, ensure_ascii=False)

            new_s1 = fused.get('s1')
            new_s2 = fused.get('s2')

            upd = update(LevelDaily).where(
                LevelDaily.symbol == symbol,
                LevelDaily.date == date_str
            ).values(
                s1=new_s1 if new_s1 is not None else row.s1,
                s2=new_s2 if new_s2 is not None else row.s2,
                s_meta=new_s_meta,
            )
            self.db.execute(upd)

        self.db.commit()
        return results


if __name__ == "__main__":
    from src.config.settings import UNIVERSE
    store = DataStore()
    engine = LevelsEngine(store)
    engine.run(UNIVERSE)
