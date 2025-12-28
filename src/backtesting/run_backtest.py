"""
Entry point for running backtests.
"""

import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

from .simple_backtest import SimpleBacktester


def main():
    """Run backtest with default parameters."""
    
    logger.info("="*70)
    logger.info("DeepValue Simple Backtest")
    logger.info("Testing buy signals without PP fusion")
    logger.info("="*70)
    
    symbols = ["QQQ", "AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOGL"]
    
    backtest = SimpleBacktester(allocation_scheme="no_s0")
    
    results = backtest.run(
        symbols=symbols,
        weeks=8
    )
    
    logger.success(f"\nBacktest completed for {len(results)} symbols")
    
    save_results(results)
    
    return results


def save_results(results: dict):
    """Save backtest results to file."""
    project_root = Path(__file__).parent.parent.parent
    output_dir = project_root / "backtest_results"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"backtest_{timestamp}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("DeepValue Backtest Results\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("="*70 + "\n\n")
        
        for symbol, result in results.items():
            f.write(result['summary_report'])
            f.write("\n\n")
            
            f.write(f"Weekly Details for {symbol}:\n")
            f.write("-"*70 + "\n")
            
            for week in result['week_results']:
                if 'report' in week:
                    f.write(week['report'])
                    f.write("\n")
            
            f.write("\n" + "="*70 + "\n\n")
    
    logger.success(f"Results saved to: {output_file}")
    print(f"\n✅ Results saved to: {output_file}")


if __name__ == "__main__":
    main()
