"""
Metrics and reporting for backtesting results.
"""

from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger


class BacktestMetrics:
    """Calculate and format backtest metrics."""
    
    @staticmethod
    def calculate_week_metrics(
        filled_orders: Dict[str, Dict],
        current_price: Optional[float] = None
    ) -> Dict:
        """
        Calculate metrics for a single week.
        
        Args:
            filled_orders: Dict of filled orders from FillSimulator
            current_price: Current price for P/L calculation
            
        Returns:
            Dict with avg_cost, total_weight, fill_count, unrealized_pnl
        """
        if not filled_orders:
            return {
                'avg_cost': None,
                'total_weight': 0.0,
                'fill_count': 0,
                'unrealized_pnl': None
            }
        
        total_weight = sum(order['alloc_pct'] for order in filled_orders.values())
        
        weighted_sum = sum(
            order['fill_price'] * order['alloc_pct']
            for order in filled_orders.values()
        )
        
        avg_cost = weighted_sum / total_weight if total_weight > 0 else None
        
        unrealized_pnl = None
        if avg_cost and current_price:
            unrealized_pnl = (current_price - avg_cost) / avg_cost * 100
        
        return {
            'avg_cost': avg_cost,
            'total_weight': total_weight,
            'fill_count': len(filled_orders),
            'unrealized_pnl': unrealized_pnl
        }
    
    @staticmethod
    def calculate_summary_metrics(
        week_results: List[Dict],
        current_price: Optional[float] = None
    ) -> Dict:
        """
        Calculate summary metrics across all weeks.
        
        Args:
            week_results: List of week result dicts
            current_price: Current price for P/L calculation
            
        Returns:
            Dict with overall metrics and fill rates
        """
        total_weeks = len(week_results)
        
        level_fills = {}
        weeks_with_fills = 0
        total_weighted_cost = 0.0
        total_weight = 0.0
        
        for week in week_results:
            filled = week.get('filled_orders', {})
            
            if filled:
                weeks_with_fills += 1
                
                for level, order in filled.items():
                    if level not in level_fills:
                        level_fills[level] = 0
                    level_fills[level] += 1
                    
                    total_weighted_cost += order['fill_price'] * order['alloc_pct']
                    total_weight += order['alloc_pct']
        
        avg_cost = total_weighted_cost / total_weight if total_weight > 0 else None
        
        fill_rates = {
            level: count / total_weeks * 100
            for level, count in level_fills.items()
        }
        
        unrealized_pnl = None
        if avg_cost and current_price:
            unrealized_pnl = (current_price - avg_cost) / avg_cost * 100
        
        return {
            'total_weeks': total_weeks,
            'weeks_with_fills': weeks_with_fills,
            'avg_cost': avg_cost,
            'total_weight': total_weight,
            'fill_rates': fill_rates,
            'level_fill_counts': level_fills,
            'unrealized_pnl': unrealized_pnl,
            'current_price': current_price
        }
    
    @staticmethod
    def format_week_report(
        symbol: str,
        signal_date: datetime,
        week_start: datetime,
        orders: List[Dict],
        filled_orders: Dict[str, Dict],
        metrics: Dict
    ) -> str:
        """Format a single week's results as a report string."""
        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"Week: {signal_date.date()} → {week_start.date()}")
        lines.append(f"Symbol: {symbol}")
        lines.append(f"{'='*70}")
        
        lines.append("\nOrders:")
        for order in orders:
            level = order['level']
            limit = order['limit_price']
            alloc = order['alloc_pct'] * 100
            
            if level in filled_orders:
                fill_info = filled_orders[level]
                fill_date = fill_info['fill_date']
                fill_price = fill_info['fill_price']
                lines.append(
                    f"  {level}: limit=${limit:.2f} ({alloc:.0f}%) "
                    f"→ Filled on {fill_date.date()} @ ${fill_price:.2f}"
                )
            else:
                lines.append(
                    f"  {level}: limit=${limit:.2f} ({alloc:.0f}%) → Not filled"
                )
        
        if metrics['avg_cost']:
            lines.append(f"\nAvg Cost: ${metrics['avg_cost']:.2f} (weighted)")
            if metrics['unrealized_pnl'] is not None:
                pnl_sign = '+' if metrics['unrealized_pnl'] >= 0 else ''
                lines.append(
                    f"Unrealized P/L: {pnl_sign}{metrics['unrealized_pnl']:.2f}%"
                )
        else:
            lines.append("\nNo fills this week")
        
        return '\n'.join(lines)
    
    @staticmethod
    def format_summary_report(
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        metrics: Dict,
        allocation_scheme: str
    ) -> str:
        """Format overall summary report."""
        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"BACKTEST SUMMARY ({metrics['total_weeks']} weeks)")
        lines.append(f"{'='*70}")
        lines.append(f"Symbol: {symbol}")
        lines.append(f"Period: {start_date.date()} to {end_date.date()}")
        lines.append(f"Allocation Scheme: {allocation_scheme}")
        lines.append(f"{'='*70}")
        
        lines.append("\nFill Rates:")
        for level in sorted(metrics['fill_rates'].keys()):
            count = metrics['level_fill_counts'][level]
            rate = metrics['fill_rates'][level]
            lines.append(f"  {level}: {count}/{metrics['total_weeks']} ({rate:.1f}%)")
        
        if metrics['avg_cost']:
            lines.append(f"\nOverall Average Cost: ${metrics['avg_cost']:.2f}")
            
            if metrics['current_price']:
                lines.append(f"Current Price: ${metrics['current_price']:.2f}")
                
                if metrics['unrealized_pnl'] is not None:
                    pnl_sign = '+' if metrics['unrealized_pnl'] >= 0 else ''
                    lines.append(
                        f"Total Unrealized P/L: {pnl_sign}{metrics['unrealized_pnl']:.2f}%"
                    )
        
        lines.append(f"\nWeeks with Fills: {metrics['weeks_with_fills']}/{metrics['total_weeks']}")
        lines.append(f"Total Weight Deployed: {metrics['total_weight']:.2f}")
        lines.append(f"{'='*70}\n")
        
        return '\n'.join(lines)
