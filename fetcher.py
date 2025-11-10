import ccxt
import pandas as pd
from datetime import datetime, timedelta
import argparse
import sys
import time
import pytz
import os
from tqdm import tqdm
import random

def generate_filename(symbol, market_type, timeframe, start_date, end_date):
    """
    Generate a descriptive filename for the output CSV
    
    Args:
        symbol (str): Trading pair symbol
        market_type (str): Market type
        timeframe (str): Candle timeframe
        start_date (str): Start date
        end_date (str): End date
    
    Returns:
        str: Generated filename
    """
    # Clean up symbol for filename
    clean_symbol = symbol.replace('/', '_')
    
    # Format dates
    start = start_date.replace('-', '')
    end = end_date.replace('-', '')
    
    # Generate filename
    filename = f"{clean_symbol}_{market_type}_{timeframe}_{start}_{end}.csv"
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    return os.path.join('data', filename)

def validate_timestamps(df, timeframe='1m', start_date=None, end_date=None):
    """
    Validate the OHLCV data for missing timestamps
    
    Args:
        df (pandas.DataFrame): DataFrame with OHLCV data
        timeframe (str): Candle timeframe (default: '1m')
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
    
    Returns:
        tuple: (bool, list) - (is_valid, list of missing timestamps)
    """
    if df.empty:
        return True, []
    
    # Convert timeframe to minutes
    timeframe_minutes = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }
    
    minutes = timeframe_minutes.get(timeframe, 1)
    
    # Use requested date range for validation
    if start_date:
        # Convert to UTC
        start_time = pd.Timestamp(start_date).tz_localize('UTC')
    else:
        start_time = df['timestamp'].min()
        
    if end_date:
        # Set end time to end of the day in UTC
        end_time = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).tz_localize('UTC') - pd.Timedelta(minutes=1)
    else:
        end_time = df['timestamp'].max()
    
    # Create expected timestamps
    expected_times = pd.date_range(start=start_time, end=end_time, freq=f'{minutes}min')
    
    # Find missing timestamps
    actual_times = pd.DatetimeIndex(df['timestamp'])
    missing_times = expected_times.difference(actual_times)
    
    return len(missing_times) == 0, list(missing_times)

def get_symbol(symbol, market_type='spot'):
    """
    Format symbol according to market type
    
    Args:
        symbol (str): Base symbol (e.g., 'BTC/USDT')
        market_type (str): Market type ('spot', 'swap', or 'futures')
    
    Returns:
        str: Formatted symbol
    """
    if market_type == 'spot':
        return symbol
    elif market_type == 'swap':
        # For perpetual futures, add '-SWAP' suffix
        base, quote = symbol.split('/')
        return f"{base}-{quote}-SWAP"
    elif market_type == 'futures':
        # For regular futures, add date suffix
        base, quote = symbol.split('/')
        return f"{base}-{quote}-FUTURES"
    else:
        raise ValueError(f"Unsupported market type: {market_type}")

def fetch_ohlcv(symbol, timeframe='1m', start_date=None, end_date=None, market_type='spot'):
    """
    Fetch OHLCV data from OKX exchange using CCXT with pagination
    
    Args:
        symbol (str): Trading pair symbol (e.g., 'BTC/USDT')
        timeframe (str): Candle timeframe (default: '1m')
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        market_type (str): Market type ('spot', 'swap', or 'futures')
    
    Returns:
        pandas.DataFrame: OHLCV data
    """
    # Initialize OKX exchange
    exchange = ccxt.okx()
    
    # Format symbol according to market type
    formatted_symbol = get_symbol(symbol, market_type)
    
    # Convert dates to timestamps (in UTC)
    if start_date:
        # Set start timestamp to beginning of the day in UTC
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        start_dt = pytz.UTC.localize(start_dt)
        start_timestamp = int(start_dt.timestamp() * 1000)
    else:
        # Default to 7 days ago if no start date provided
        start_timestamp = int((datetime.now(pytz.UTC) - timedelta(days=7)).timestamp() * 1000)
        
    if end_date:
        # Set end timestamp to end of the day in UTC
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        end_dt = pytz.UTC.localize(end_dt)
        end_timestamp = int(end_dt.timestamp() * 1000 - 1)
    else:
        end_timestamp = int(datetime.now(pytz.UTC).timestamp() * 1000)
    
    # Calculate total time range in minutes
    total_minutes = (end_timestamp - start_timestamp) // (60 * 1000)
    
    # Create progress bar for overall progress
    pbar = tqdm(total=total_minutes, 
               desc=f"Fetching {formatted_symbol} {timeframe} data",
               unit="min")
    
    all_candles = []
    current_timestamp = start_timestamp
    
    # Retry configuration
    max_retries = 5
    base_delay = 2  # Base delay in seconds
    
    while current_timestamp < end_timestamp:
        # Retry mechanism with exponential backoff
        retry_count = 0
        success = False
        
        while not success and retry_count < max_retries:
            try:
                # Fetch OHLCV data with pagination
                candles = exchange.fetch_ohlcv(
                    formatted_symbol,
                    timeframe=timeframe,
                    since=current_timestamp,
                    limit=100  # Maximum limit per request
                )
                
                success = True  # If we reach here, the request was successful
                
            except ccxt.NetworkError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"\nNetwork error after {max_retries} retries: {e}")
                    print(f"Saving partial data collected so far...")
                    break
                
                # Calculate exponential backoff delay
                delay = base_delay * (2 ** (retry_count - 1)) + (random.random() * 0.5)
                print(f"\nNetwork error: {e}. Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
                time.sleep(delay)
                
            except ccxt.ExchangeError as e:
                # Check if it's a timeout error
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"\nTimeout error after {max_retries} retries: {e}")
                        print(f"Saving partial data collected so far...")
                        break
                    
                    # Calculate exponential backoff delay
                    delay = base_delay * (2 ** (retry_count - 1)) + (random.random() * 0.5)
                    print(f"\nTimeout error: {e}. Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
                    time.sleep(delay)
                else:
                    # For other exchange errors, log and continue
                    print(f"\nExchange error: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"Failed after {max_retries} retries. Saving partial data collected so far...")
                        break
                    
                    delay = base_delay * (2 ** (retry_count - 1)) + (random.random() * 0.5)
                    print(f"Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
                    time.sleep(delay)
                    
            except Exception as e:
                print(f"\nUnexpected error: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"Failed after {max_retries} retries. Saving partial data collected so far...")
                    break
                
                delay = base_delay * (2 ** (retry_count - 1)) + (random.random() * 0.5)
                print(f"Retrying in {delay:.2f} seconds (attempt {retry_count}/{max_retries})...")
                time.sleep(delay)
        
        # If all retries failed, exit the loop
        if not success:
            break
            
        # If no candles returned even after successful request, break
        if not candles:
            break
            
        all_candles.extend(candles)
        
        # Update progress bar
        minutes_fetched = len(candles)
        pbar.update(minutes_fetched)
        
        # Update timestamp for next iteration
        # Add 1 minute to avoid duplicate candles
        current_timestamp = candles[-1][0] + (60 * 1000)  # Add 1 minute in milliseconds
        
        # Add a small delay to avoid rate limiting
        time.sleep(0.5)
    
    pbar.close()
    
    if not all_candles:
        print("No data found for the specified period")
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Convert timestamp to datetime with UTC timezone
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    
    # Filter data within the specified date range
    df = df[(df['timestamp'] >= pd.Timestamp(start_timestamp, unit='ms', tz='UTC')) &
            (df['timestamp'] <= pd.Timestamp(end_timestamp, unit='ms', tz='UTC'))]
    
    # Remove any duplicate timestamps
    df = df.drop_duplicates(subset=['timestamp'])
    
    # Sort by timestamp
    df = df.sort_values('timestamp')
    
    return df

def main():
    parser = argparse.ArgumentParser(description='Fetch OHLCV data from OKX')
    parser.add_argument('--symbol', type=str, default='BTC/USDT',
                      help='Trading pair symbol (default: BTC/USDT)')
    parser.add_argument('--timeframe', type=str, default='1m',
                      help='Candle timeframe (default: 1m)')
    parser.add_argument('--start-date', type=str,
                      help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str,
                      help='End date in YYYY-MM-DD format')
    parser.add_argument('--output', type=str,
                      help='Output CSV file name (optional, will be auto-generated if not provided)')
    parser.add_argument('--market-type', type=str, default='spot',
                      choices=['spot', 'swap', 'futures'],
                      help='Market type: spot, swap (perpetual futures), or futures (default: spot)')
    
    args = parser.parse_args()
    
    # Generate output filename if not provided
    if not args.output:
        args.output = generate_filename(
            args.symbol,
            args.market_type,
            args.timeframe,
            args.start_date or datetime.now().strftime('%Y-%m-%d'),
            args.end_date or datetime.now().strftime('%Y-%m-%d')
        )
    
    # Fetch data
    df = fetch_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=args.start_date,
        end_date=args.end_date,
        market_type=args.market_type
    )
    
    if not df.empty:
        # Validate timestamps
        is_valid, missing_times = validate_timestamps(
            df, 
            args.timeframe,
            args.start_date,
            args.end_date
        )
        
        if not is_valid:
            print("\nWARNING: Missing timestamps detected!")
            print(f"Total missing candles: {len(missing_times)}")
            print("\nFirst 10 missing timestamps:")
            for ts in missing_times[:10]:
                print(f"  {ts}")
            if len(missing_times) > 10:
                print(f"  ... and {len(missing_times) - 10} more")
        else:
            print("\nData validation passed: No missing timestamps")
        
        # Save to CSV
        df.to_csv(args.output, index=False)
        print(f"\nData saved to {args.output}")
        print(f"Total candles: {len(df)}")
        print(f"Date range: from {df['timestamp'].min()} to {df['timestamp'].max()}")

if __name__ == "__main__":
    main() 