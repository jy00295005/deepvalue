"""
Signal generator for backtesting.
Generates limit orders based on dynamically calculated levels at each time point.
"""

from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from .levels_calculator import BacktestLevelsCalculator


class SignalGenerator:
    """Generate buy signals from dynamically calculated levels."""
    
    ALLOCATION_SCHEMES = {
        "conservative": {
            "S0": 0.15,
            "S1": 0.30,
            "S2": 0.30,
            "S3": 0.25,
        },
        "aggressive": {
            "S0": 0.40,
            "S1": 0.30,
            "S2": 0.20,
            "S3": 0.10,
        },
        "no_s0": {
            "S1": 0.20,
            "S2": 0.30,
            "S3": 0.40,
            # reserve: 10% (not deployed)
        }
    }
    
    def __init__(self, allocation_scheme: str = "conservative"):
        self.levels_calculator = BacktestLevelsCalculator()
        self.allocation_scheme = allocation_scheme
        self.allocations = self.ALLOCATION_SCHEMES.get(
            allocation_scheme, 
            self.ALLOCATION_SCHEMES["conservative"]
        )
        logger.info(f"SignalGenerator initialized with {allocation_scheme} allocation")
    
    def generate_orders(
        self, 
        symbol: str, 
        as_of_date: datetime
    ) -> List[Dict]:
        """
        Generate limit orders for a given symbol and date.
        Dynamically calculates levels using only data available at as_of_date.
        
        Args:
            symbol: Stock symbol
            as_of_date: Signal generation date (typically Sunday)
            
        Returns:
            List of order dicts with level, limit_price, alloc_pct
        """
        # Dynamically calculate levels using only data available at this time point
        levels = self.levels_calculator.compute_levels_at_date(symbol, as_of_date)
        
        if not levels:
            logger.warning(f"No levels calculated for {symbol} on {as_of_date.date()}")
            return []
        
        orders = []
        
        for level_name, alloc_pct in self.allocations.items():
            level_key = level_name.lower()
            
            if level_key not in levels or levels[level_key] is None:
                logger.debug(f"Level {level_name} not available for {symbol}")
                continue
            
            support_value = levels[level_key]
            band_width = levels.get('band_width', 0.02)
            
            # Use band_high as limit price (easier to fill)
            band_high = support_value * (1 + band_width / 2)
            
            orders.append({
                "level": level_name,
                "support_value": support_value,
                "limit_price": band_high,
                "alloc_pct": alloc_pct,
                "band_width": band_width,
                "current_price": levels.get('current_price')
            })
        
        logger.info(
            f"Generated {len(orders)} orders for {symbol} on {as_of_date.date()} "
            f"(price: {levels.get('current_price', 'N/A'):.2f})"
        )
        return orders
