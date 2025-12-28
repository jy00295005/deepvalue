"""
Levels calculator for backtesting.
Computes support levels for a specific point in time using only data available at that time.
"""

from datetime import datetime, date
from typing import Dict, List, Optional
import pandas as pd
from loguru import logger
from sqlalchemy import and_

from src.data.store import DataStore, PriceDaily


class BacktestLevelsCalculator:
    """Calculate levels for backtesting at specific points in time."""
    
    def __init__(self):
        self.db = DataStore()
    
    def compute_levels_at_date(
        self, 
        symbol: str, 
        as_of_date: datetime
    ) -> Optional[Dict]:
        """
        Compute support levels for a symbol using only data available up to as_of_date.
        
        Args:
            symbol: Stock symbol
            as_of_date: The date to compute levels for (e.g., a Sunday)
            
        Returns:
            Dict with s0, s1, s2, s3, band_width or None if insufficient data
        """
        # Load price data up to as_of_date
        df = self._load_prices_up_to(symbol, as_of_date)
        
        if df.empty or len(df) < 50:
            logger.warning(f"Insufficient price data for {symbol} up to {as_of_date.date()}")
            return None
        
        # Calculate levels using the levels engine logic
        levels = self._calculate_levels_from_df(df, symbol, as_of_date)
        
        if not levels:
            return None
        
        # S0 = S1 * 1.10 (10% above S1, easier to fill)
        s1 = levels.get('s1')
        s0 = s1 * 1.10 if s1 else None
        
        return {
            's0': s0,
            's1': levels.get('s1'),
            's2': levels.get('s2'),
            's3': levels.get('s3'),
            'band_width': 0.02,  # Fixed 2% band width
            'current_price': levels.get('current_price'),
            'as_of_date': as_of_date.date()
        }
    
    def _load_prices_up_to(self, symbol: str, as_of_date: datetime) -> pd.DataFrame:
        """Load price data up to (and including) as_of_date."""
        with self.db.get_session() as session:
            rows = session.query(PriceDaily).filter(
                and_(
                    PriceDaily.symbol == symbol,
                    PriceDaily.date <= as_of_date.date()
                )
            ).order_by(PriceDaily.date).all()
            
            if not rows:
                return pd.DataFrame()
            
            data = []
            for r in rows:
                data.append({
                    'date': pd.to_datetime(r.date),
                    'open': r.open,
                    'high': r.high,
                    'low': r.low,
                    'close': r.close,
                    'adj_close': r.adj_close,
                    'volume': r.volume
                })
            
            df = pd.DataFrame(data)
            df.set_index('date', inplace=True)
            df.sort_index(inplace=True)
            
            return df
    
    def _calculate_levels_from_df(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        as_of_date: datetime
    ) -> Optional[Dict]:
        """
        Calculate S1/S2/S3 levels from price dataframe.
        Uses simplified logic based on structural supports.
        """
        if df.empty:
            return None
        
        # Get current price (last available price)
        current_price = df['adj_close'].iloc[-1] if pd.notna(df['adj_close'].iloc[-1]) else df['close'].iloc[-1]
        
        # Calculate SMAs
        df['sma20'] = df['adj_close'].fillna(df['close']).rolling(20).mean()
        df['sma50'] = df['adj_close'].fillna(df['close']).rolling(50).mean()
        df['sma200'] = df['adj_close'].fillna(df['close']).rolling(200).mean()
        
        # Find swing lows (simple implementation)
        swing_lows = self._find_swing_lows(df, window=5)
        
        # Get support candidates
        candidates = []
        
        # Add SMA supports if below current price
        latest_sma20 = df['sma20'].iloc[-1]
        latest_sma50 = df['sma50'].iloc[-1]
        latest_sma200 = df['sma200'].iloc[-1]
        
        if pd.notna(latest_sma20) and latest_sma20 < current_price:
            candidates.append({
                'price': latest_sma20,
                'source': 'sma20',
                'strength': 1.0,
                'distance_pct': (current_price - latest_sma20) / current_price
            })
        
        if pd.notna(latest_sma50) and latest_sma50 < current_price:
            candidates.append({
                'price': latest_sma50,
                'source': 'sma50',
                'strength': 1.5,
                'distance_pct': (current_price - latest_sma50) / current_price
            })
        
        if pd.notna(latest_sma200) and latest_sma200 < current_price:
            candidates.append({
                'price': latest_sma200,
                'source': 'sma200',
                'strength': 2.0,
                'distance_pct': (current_price - latest_sma200) / current_price
            })
        
        # Add structural supports from swing lows
        for lookback_years in [1, 3, 5]:
            lookback_days = lookback_years * 252
            recent_swings = swing_lows.tail(lookback_days)
            
            if len(recent_swings) > 0:
                # Cluster swing lows
                clusters = self._cluster_prices(recent_swings['low'].values, tolerance=0.03)
                
                for cluster_price, count in clusters:
                    if cluster_price < current_price:
                        candidates.append({
                            'price': cluster_price,
                            'source': f'struct_{lookback_years}y',
                            'strength': count * (1 + lookback_years * 0.1),
                            'distance_pct': (current_price - cluster_price) / current_price
                        })
        
        if not candidates:
            logger.warning(f"No support candidates found for {symbol}")
            return None
        
        # Sort by distance (closest first) and select S1, S2, S3
        candidates.sort(key=lambda x: x['distance_pct'])
        
        # Filter to only supports within reasonable range (2% - 50% below)
        valid_candidates = [c for c in candidates if 0.02 <= c['distance_pct'] <= 0.50]
        
        if not valid_candidates:
            # Fallback: use any candidates below price
            valid_candidates = [c for c in candidates if c['distance_pct'] > 0]
        
        s1 = valid_candidates[0]['price'] if len(valid_candidates) > 0 else None
        s2 = valid_candidates[1]['price'] if len(valid_candidates) > 1 else None
        s3 = valid_candidates[2]['price'] if len(valid_candidates) > 2 else None
        
        return {
            's1': s1,
            's2': s2,
            's3': s3,
            'current_price': current_price,
            'candidates': valid_candidates[:5]
        }
    
    def _find_swing_lows(self, df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
        """Find swing lows in price data."""
        lows = df['low'].copy()
        swing_mask = (
            (lows.shift(window) > lows) & 
            (lows.shift(-window) > lows)
        )
        return df[swing_mask]
    
    def _cluster_prices(self, prices: list, tolerance: float = 0.03) -> List[tuple]:
        """
        Cluster prices within tolerance and return (cluster_center, count).
        """
        if len(prices) == 0:
            return []
        
        prices = sorted(prices)
        clusters = []
        current_cluster = [prices[0]]
        
        for p in prices[1:]:
            if (p - current_cluster[0]) / current_cluster[0] <= tolerance:
                current_cluster.append(p)
            else:
                # Save current cluster
                cluster_center = sum(current_cluster) / len(current_cluster)
                clusters.append((cluster_center, len(current_cluster)))
                current_cluster = [p]
        
        # Don't forget the last cluster
        if current_cluster:
            cluster_center = sum(current_cluster) / len(current_cluster)
            clusters.append((cluster_center, len(current_cluster)))
        
        # Sort by count (most touches first)
        clusters.sort(key=lambda x: -x[1])
        
        return clusters
