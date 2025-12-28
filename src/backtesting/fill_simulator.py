"""
Fill simulator for backtesting.
Simulates order fills based on historical price data.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
from loguru import logger
from sqlalchemy import and_

from src.data.store import DataStore, PriceDaily


class FillSimulator:
    """Simulate order fills based on historical daily bars."""
    
    def __init__(self):
        self.db = DataStore()
    
    def simulate_week(
        self, 
        symbol: str, 
        orders: List[Dict], 
        week_start_date: datetime
    ) -> Dict[str, Dict]:
        """
        Simulate order fills for one week.
        
        Args:
            symbol: Stock symbol
            orders: List of order dicts from SignalGenerator
            week_start_date: Start date of the week (typically Monday after signal)
            
        Returns:
            Dict mapping level name to fill info:
            {
                "S1": {
                    "fill_price": 450.50,
                    "fill_date": datetime(...),
                    "alloc_pct": 0.30,
                    "limit_price": 450.50
                },
                ...
            }
        """
        trading_days = self._get_trading_days(symbol, week_start_date, days=5)
        
        if not trading_days:
            logger.warning(
                f"No trading days found for {symbol} starting {week_start_date.date()}"
            )
            return {}
        
        filled_orders = {}
        
        for day_data in trading_days:
            daily_low = day_data['low']
            trade_date = day_data['date']
            
            for order in orders:
                level = order["level"]
                limit_price = order["limit_price"]
                
                if level not in filled_orders and daily_low <= limit_price:
                    filled_orders[level] = {
                        "fill_price": limit_price,
                        "fill_date": trade_date,
                        "alloc_pct": order["alloc_pct"],
                        "limit_price": limit_price,
                        "support_value": order["support_value"]
                    }
                    logger.debug(
                        f"{symbol} {level} filled on {trade_date.date()} "
                        f"@ ${limit_price:.2f} (low=${daily_low:.2f})"
                    )
        
        logger.info(
            f"{symbol}: {len(filled_orders)}/{len(orders)} orders filled in week "
            f"starting {week_start_date.date()}"
        )
        
        return filled_orders
    
    def _get_trading_days(
        self, 
        symbol: str, 
        start_date: datetime, 
        days: int = 5
    ) -> List[Dict]:
        """
        Get trading days data for the next N days.
        
        Args:
            symbol: Stock symbol
            start_date: Start date
            days: Number of trading days to fetch
            
        Returns:
            List of dicts with date, low, close
        """
        end_date = start_date + timedelta(days=days+5)
        
        with self.db.get_session() as session:
            bars = session.query(PriceDaily).filter(
                and_(
                    PriceDaily.symbol == symbol,
                    PriceDaily.date >= start_date.date(),
                    PriceDaily.date <= end_date.date()
                )
            ).order_by(PriceDaily.date).limit(days).all()
            
            return [
                {
                    'date': pd.to_datetime(bar.date) if isinstance(bar.date, str) else bar.date,
                    'low': bar.low,
                    'close': bar.close,
                    'high': bar.high
                }
                for bar in bars
            ]
