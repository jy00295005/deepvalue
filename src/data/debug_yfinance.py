import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def debug_yfinance():
    symbol = "AAPL"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    print(f"Downloading {symbol} from {start_date} to {end_date} with auto_adjust=False...")
    df = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=False)
    
    print("Columns:", df.columns)
    if isinstance(df.columns, pd.MultiIndex):
        print("MultiIndex Levels:", df.columns.levels)
        # Check if flattening works as expected
        df.columns = df.columns.get_level_values(0)
        print("Flattened Columns:", df.columns)
        
    df = df.reset_index()
    df.columns = [c.lower().replace(' ', '_') for c in df.columns]
    print("Final Columns:", df.columns)
    print("First row:", df.iloc[0].to_dict())

if __name__ == "__main__":
    debug_yfinance()
