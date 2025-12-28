"""
Simple backtesting engine for DeepValue strategy.
Tests historical buy signals without PP fusion.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger
from sqlalchemy import and_

from src.data.store import DataStore, PriceDaily
from .signal_generator import SignalGenerator
from .fill_simulator import FillSimulator
from .metrics import BacktestMetrics


class SimpleBacktester:
    """Main backtesting engine."""
    
    def __init__(self, allocation_scheme: str = "conservative"):
        self.db = DataStore()
        self.signal_generator = SignalGenerator(allocation_scheme)
        self.fill_simulator = FillSimulator()
        self.metrics = BacktestMetrics()
        self.allocation_scheme = allocation_scheme
    
    def run(
        self,
        symbols: List[str],
        weeks: int = 8,
        end_date: Optional[datetime] = None
    ) -> dict:
        """
        Run backtest for given symbols.
        
        Args:
            symbols: List of stock symbols to test
            weeks: Number of weeks to backtest
            end_date: End date for backtest (default: most recent Sunday)
            
        Returns:
            Dict mapping symbol to backtest results
        """
        if end_date is None:
            end_date = self._get_most_recent_sunday()
        
        start_date = end_date - timedelta(weeks=weeks)
        
        logger.info(
            f"Starting backtest for {len(symbols)} symbols, "
            f"{weeks} weeks ({start_date.date()} to {end_date.date()})"
        )
        
        results = {}
        
        for symbol in symbols:
            logger.info(f"\n{'='*70}")
            logger.info(f"Backtesting {symbol}")
            logger.info(f"{'='*70}")
            
            symbol_result = self._backtest_symbol(
                symbol, start_date, end_date, weeks
            )
            results[symbol] = symbol_result
        
        return results
    
    def _backtest_symbol(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        weeks: int
    ) -> dict:
        """Run backtest for a single symbol."""
        sundays = self._get_sundays(start_date, end_date)
        
        if len(sundays) < weeks:
            logger.warning(
                f"Only found {len(sundays)} Sundays, expected {weeks}"
            )
        
        week_results = []
        
        for sunday in sundays:
            week_result = self._backtest_week(symbol, sunday)
            week_results.append(week_result)
        
        current_price = self._get_current_price(symbol)
        
        summary_metrics = self.metrics.calculate_summary_metrics(
            week_results, current_price
        )
        
        summary_report = self.metrics.format_summary_report(
            symbol, start_date, end_date, summary_metrics, self.allocation_scheme
        )
        
        logger.info(summary_report)
        
        return {
            'symbol': symbol,
            'start_date': start_date,
            'end_date': end_date,
            'weeks': len(week_results),
            'week_results': week_results,
            'summary_metrics': summary_metrics,
            'summary_report': summary_report
        }
    
    def _backtest_week(self, symbol: str, signal_date: datetime) -> dict:
        """Backtest a single week."""
        orders = self.signal_generator.generate_orders(symbol, signal_date)
        
        if not orders:
            logger.warning(f"No orders generated for {symbol} on {signal_date.date()}")
            return {
                'signal_date': signal_date,
                'week_start': signal_date + timedelta(days=1),
                'orders': [],
                'filled_orders': {},
                'metrics': self.metrics.calculate_week_metrics({})
            }
        
        week_start = signal_date + timedelta(days=1)
        
        filled_orders = self.fill_simulator.simulate_week(
            symbol, orders, week_start
        )
        
        current_price = self._get_current_price(symbol)
        week_metrics = self.metrics.calculate_week_metrics(filled_orders, current_price)
        
        week_report = self.metrics.format_week_report(
            symbol, signal_date, week_start, orders, filled_orders, week_metrics
        )
        
        logger.info(week_report)
        
        return {
            'signal_date': signal_date,
            'week_start': week_start,
            'orders': orders,
            'filled_orders': filled_orders,
            'metrics': week_metrics,
            'report': week_report
        }
    
    def _get_sundays(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Get all Sundays between start and end dates."""
        sundays = []
        current = start_date
        
        while current.weekday() != 6:
            current += timedelta(days=1)
        
        while current <= end_date:
            sundays.append(current)
            current += timedelta(days=7)
        
        return sundays
    
    def _get_most_recent_sunday(self) -> datetime:
        """Get the most recent Sunday."""
        today = datetime.now()
        days_since_sunday = (today.weekday() + 1) % 7
        most_recent_sunday = today - timedelta(days=days_since_sunday)
        return most_recent_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the most recent closing price for a symbol."""
        with self.db.get_session() as session:
            latest_bar = session.query(PriceDaily).filter(
                PriceDaily.symbol == symbol
            ).order_by(PriceDaily.date.desc()).first()
            
            if latest_bar:
                return latest_bar.close
            
            return None
