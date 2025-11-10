import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
from datetime import datetime
import numpy as np
import os
import re

def generate_output_filename(spot_file, futures_file, threshold):
    """
    Generate an output filename based on the input files.
    
    Args:
        spot_file: Path to spot CSV file
        futures_file: Path to futures CSV file
        threshold: Threshold percentage for profitable trades
        
    Returns:
        A string with the generated output filename
    """
    # Extract asset names from filenames
    spot_base = os.path.basename(spot_file)
    futures_base = os.path.basename(futures_file)
    
    # Try to extract asset name and date range
    spot_match = re.search(r'([A-Z]+)_([A-Z]+)_(\w+)_(\w+)_(\d+)_(\d+)', spot_base)
    
    if spot_match:
        # If filename follows a pattern like BTC_USDT_spot_1m_20250315_20250515.csv
        asset = f"{spot_match.group(1)}_{spot_match.group(2)}"
        time_period = f"{spot_match.group(5)[:8]}_to_{spot_match.group(6)[:8]}"
        output_name = f"{asset}_cash_and_carry_th{threshold}_{time_period}.png"
    else:
        # If filename doesn't follow the pattern, use a simpler approach
        spot_name = os.path.splitext(spot_base)[0]
        futures_name = os.path.splitext(os.path.basename(futures_file))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"cash_and_carry_{spot_name}_vs_{futures_name}_{timestamp}.png"
    
    return output_name

def load_and_process_data(spot_file, futures_file, timestamp_format=None):
    """
    Load CSV files, sync by timestamp, and calculate percentage difference.
    
    Args:
        spot_file: Path to spot CSV file
        futures_file: Path to futures CSV file
        timestamp_format: Optional format string for timestamp parsing
    
    Returns:
        Processed DataFrame with both prices and percentage difference
    """
    # Load CSVs
    spot_df = pd.read_csv(spot_file)
    futures_df = pd.read_csv(futures_file)
    
    # Convert timestamps if format is provided
    if timestamp_format:
        spot_df['timestamp'] = pd.to_datetime(spot_df['timestamp'], format=timestamp_format)
        futures_df['timestamp'] = pd.to_datetime(futures_df['timestamp'], format=timestamp_format)
    else:
        spot_df['timestamp'] = pd.to_datetime(spot_df['timestamp'])
        futures_df['timestamp'] = pd.to_datetime(futures_df['timestamp'])
    
    # Set timestamp as index
    spot_df.set_index('timestamp', inplace=True)
    futures_df.set_index('timestamp', inplace=True)
    
    # Merge dataframes on timestamp index
    merged_df = pd.DataFrame()
    merged_df['spot_price'] = spot_df['close']
    merged_df['futures_price'] = futures_df['close']
    
    # Remove rows with NaN values (timestamps that don't match)
    merged_df = merged_df.dropna()
    
    # Calculate percentage difference using mean of both prices
    # This creates a more symmetric percentage difference
    merged_df['pct_diff'] = ((merged_df['futures_price'] - merged_df['spot_price']) / 
                             ((merged_df['futures_price'] + merged_df['spot_price']) / 2)) * 100
    
    return merged_df

def plot_analysis(data, threshold=0.15, output_file=None, display=True, capital_history=None, exposure_history=None):
    """
    Create plots for cash-and-carry analysis.
    Optionally includes equity and exposure plots if provided.
    
    Args:
        data: DataFrame with spot_price, futures_price, and pct_diff columns
        threshold: Threshold percentage for profitable trades after fees
        output_file: Optional file path to save the plot
        display: Whether to display the plot (in addition to saving)
        capital_history: List of equity values over time (optional)
        exposure_history: List of exposure values over time (optional, in %)
    """
    n_subplots = 2
    if capital_history is not None and exposure_history is not None:
        n_subplots = 4
    
    fig, axes = plt.subplots(n_subplots, 1, figsize=(14, 4*n_subplots), gridspec_kw={'height_ratios': [2, 1] + [1]*(n_subplots-2)})
    if n_subplots == 2:
        ax1, ax2 = axes
    else:
        ax1, ax2, ax3, ax4 = axes
    
    # Format dates for x-axis
    date_format = mdates.DateFormatter('%Y-%m-%d')
    
    # Plot 1: Price charts
    ax1.plot(data.index, data['spot_price'], label='Spot Price', color='blue')
    ax1.plot(data.index, data['futures_price'], label='Futures Price', color='red')
    ax1.set_title('Spot vs Futures Prices')
    ax1.set_ylabel('Price')
    ax1.legend()
    ax1.grid(True)
    ax1.xaxis.set_major_formatter(date_format)
    
    # Plot 2: Percentage difference
    ax2.plot(data.index, data['pct_diff'], label='% Difference', color='green')
    ax2.axhline(y=threshold, color='r', linestyle='-', label=f'+{threshold}% (Profit Threshold)')
    ax2.axhline(y=-threshold, color='r', linestyle='-', label=f'-{threshold}% (Profit Threshold)')
    ax2.axhline(y=0, color='black', linestyle='--')
    ax2.set_title('Symmetric Percentage Difference (Futures - Spot)/Mean(Futures,Spot)')
    ax2.set_ylabel('Difference (%)')
    ax2.set_xlabel('Date')
    ax2.legend()
    ax2.grid(True)
    ax2.xaxis.set_major_formatter(date_format)
    
    # Add some stats on the plot
    mean_diff = data['pct_diff'].mean()
    max_diff = data['pct_diff'].max()
    min_diff = data['pct_diff'].min()
    std_diff = data['pct_diff'].std()
    
    stats_text = (f"Mean: {mean_diff:.3f}%\n"
                  f"Max: {max_diff:.3f}%\n"
                  f"Min: {min_diff:.3f}%\n"
                  f"Std Dev: {std_diff:.3f}%")
    
    # Place text in the upper right corner of the percentage difference plot
    ax2.text(0.95, 0.95, stats_text, transform=ax2.transAxes, 
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # Calculate profitable opportunities
    profitable_periods = data[abs(data['pct_diff']) > threshold]
    profitable_pct = len(profitable_periods) / len(data) * 100 if len(data) > 0 else 0
    
    # Add opportunity analysis to plot
    opportunity_text = (f"Opportunities: {len(profitable_periods)} periods\n"
                       f"({profitable_pct:.2f}% of total)")
    
    ax2.text(0.05, 0.95, opportunity_text, transform=ax2.transAxes,
             verticalalignment='top', horizontalalignment='left',
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # Plot 3: Equity (capital) over time
    if n_subplots > 2:
        ax3.plot(data.index, capital_history, label='Equity', color='purple')
        ax3.set_title('Equity (Capital) Over Time')
        ax3.set_ylabel('Equity ($)')
        ax3.grid(True)
        ax3.legend()
        ax3.xaxis.set_major_formatter(date_format)
    
    # Plot 4: Exposure over time
    if n_subplots > 2:
        ax4.plot(data.index, exposure_history, label='Exposure (%)', color='orange')
        ax4.set_title('Exposure Over Time')
        ax4.set_ylabel('Exposure (%)')
        ax4.set_xlabel('Date')
        ax4.grid(True)
        ax4.legend()
        ax4.xaxis.set_major_formatter(date_format)
    
    plt.tight_layout()
    
    # Always save the plot
    if output_file:
        plt.savefig(output_file)
        print(f"Plot saved to {output_file}")
    
    # Display plot if requested
    if display:
        plt.show()
    else:
        plt.close(fig)

def backtest_strategy(data, entrance_threshold, exit_threshold, initial_capital=10000):
    """
    Backtest a cash-and-carry strategy using entrance/exit thresholds.
    Trades both contango and backwardation. Uses 10% of capital for 10x leveraged spot and 10% for 10x leveraged futures.
    
    Args:
        data: DataFrame with 'spot_price', 'futures_price', 'pct_diff'
        entrance_threshold: Threshold to enter a trade (absolute value, in %)
        exit_threshold: Threshold to exit a trade (absolute value, in %)
        initial_capital: Starting capital (default $10,000)
    Returns:
        Dictionary with backtest results
    """
    position = None  # None, 'contango', or 'backwardation'
    entry_price_spot = 0
    entry_price_futures = 0
    trades = []
    capital = initial_capital
    capital_history = []
    exposure_history = []
    trade_size = 0.1 * capital  # 10% of capital for each leg
    leverage = 10
    n = len(data)
    
    # Fee rates
    futures_fee_rate = 0.0014  # 0.14% for futures (0.07% * 2 for entry and exit)
    margin_fee_rate = 0.0018   # 0.18% for margin trading
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        pct_diff = row['pct_diff']
        spot = row['spot_price']
        futures = row['futures_price']
        capital_history.append(capital)
        # Exposure: 20% when in position, 0% otherwise
        if position is not None:
            exposure_history.append(20)
        else:
            exposure_history.append(0)
        
        if position is None:
            # Entry conditions
            if pct_diff > entrance_threshold:
                # Contango: Short futures, long spot
                position = 'contango'
                entry_price_spot = spot
                entry_price_futures = futures
                entry_index = i
                entry_time = timestamp
            elif pct_diff < -entrance_threshold:
                # Backwardation: Long futures, short spot
                position = 'backwardation'
                entry_price_spot = spot
                entry_price_futures = futures
                entry_index = i
                entry_time = timestamp
        else:
            # Exit conditions
            if (position == 'contango' and pct_diff < exit_threshold) or \
               (position == 'backwardation' and pct_diff > -exit_threshold):
                # Close position
                exit_price_spot = spot
                exit_price_futures = futures
                exit_index = i
                exit_time = timestamp
                
                # Calculate fees
                spot_volume = trade_size * leverage
                futures_volume = trade_size * leverage
                spot_fees = spot_volume * margin_fee_rate
                futures_fees = futures_volume * futures_fee_rate
                total_fees = spot_fees + futures_fees
                
                # Calculate PnL for each leg
                if position == 'contango':
                    # Long spot (10x), short futures (10x)
                    spot_pnl = ((exit_price_spot - entry_price_spot) / entry_price_spot) * trade_size * leverage
                    futures_pnl = ((entry_price_futures - exit_price_futures) / entry_price_futures) * trade_size * leverage
                else:
                    # Short spot (10x), long futures (10x)
                    spot_pnl = ((entry_price_spot - exit_price_spot) / entry_price_spot) * trade_size * leverage
                    futures_pnl = ((exit_price_futures - entry_price_futures) / entry_price_futures) * trade_size * leverage
                
                # Subtract fees from PnL
                spot_pnl -= spot_fees
                futures_pnl -= futures_fees
                total_pnl = spot_pnl + futures_pnl
                
                capital += total_pnl
                trades.append({
                    'type': position,
                    'entry_time': entry_time,
                    'exit_time': exit_time,
                    'entry_index': entry_index,
                    'exit_index': exit_index,
                    'entry_spot': entry_price_spot,
                    'entry_futures': entry_price_futures,
                    'exit_spot': exit_price_spot,
                    'exit_futures': exit_price_futures,
                    'spot_pnl': spot_pnl,
                    'futures_pnl': futures_pnl,
                    'total_pnl': total_pnl,
                    'spot_fees': spot_fees,
                    'futures_fees': futures_fees,
                    'total_fees': total_fees
                })
                # Reset
                position = None
                entry_price_spot = 0
                entry_price_futures = 0
                trade_size = 0.1 * capital  # Update trade size with new capital
    # Final capital and exposure history
    capital_history += [capital] * (n - len(capital_history))
    exposure_history += [0] * (n - len(exposure_history))
    # Backtest summary
    total_trades = len(trades)
    wins = sum(1 for t in trades if t['total_pnl'] > 0)
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = capital - initial_capital
    total_fees = sum(t['total_fees'] for t in trades)
    results = {
        'initial_capital': initial_capital,
        'final_capital': capital,
        'total_pnl': total_pnl,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'trades': trades,
        'capital_history': capital_history,
        'exposure_history': exposure_history,
        'total_fees': total_fees
    }
    return results

def print_backtest_results(results):
    print("\nBacktest Results:")
    print(f"Initial capital: ${results['initial_capital']:.2f}")
    print(f"Final capital:   ${results['final_capital']:.2f}")
    print(f"Total PnL:       ${results['total_pnl']:.2f}")
    print(f"Total fees:      ${results['total_fees']:.2f}")
    print(f"Total trades:    {results['total_trades']}")
    print(f"Win rate:        {results['win_rate']:.2f}%")
    if results['total_trades'] > 0:
        print(f"Avg PnL/trade:   ${results['total_pnl']/results['total_trades']:.2f}")
        print(f"Avg fees/trade:  ${results['total_fees']/results['total_trades']:.2f}")
    print()
    for i, t in enumerate(results['trades']):
        print(f"Trade {i+1}: {t['type']} | Entry: {t['entry_time']} | Exit: {t['exit_time']} | PnL: ${t['total_pnl']:.2f} | Fees: ${t['total_fees']:.2f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cash-and-Carry Analysis Tool')
    parser.add_argument('spot_file', type=str, help='Path to spot CSV file')
    parser.add_argument('futures_file', type=str, help='Path to futures CSV file')
    parser.add_argument('--threshold', type=float, default=0.15, 
                        help='Threshold percentage for profitable trades (default: 0.15)')
    parser.add_argument('--entrance', type=float, default=0.3, 
                        help='Entrance threshold for backtest (in %, default: 0.3)')
    parser.add_argument('--exit', type=float, default=0.1, 
                        help='Exit threshold for backtest (in %, default: 0.1)')
    parser.add_argument('--capital', type=float, default=10000, 
                        help='Initial capital for backtest (default: 10000)')
    parser.add_argument('--timestamp_format', type=str, 
                        help='Format string for timestamp parsing (e.g., "%%Y-%%m-%%d %%H:%%M:%%S")')
    parser.add_argument('--output', type=str, 
                        help='Output file path for saving the plot (autogenerated if not specified)')
    parser.add_argument('--display', action='store_true', default=True,
                        help='Display the plot (in addition to saving)')
    
    args = parser.parse_args()
    
    # Process data
    data = load_and_process_data(args.spot_file, args.futures_file, args.timestamp_format)
    
    # Generate output filename if not provided
    output_file = args.output
    if not output_file:
        output_file = generate_output_filename(args.spot_file, args.futures_file, args.threshold)
    
    # Run backtest
    results = backtest_strategy(data, args.entrance, args.exit, args.capital)
    
    # Create plot (with equity and exposure if available)
    plot_analysis(
        data,
        args.threshold,
        output_file,
        args.display,
        capital_history=results['capital_history'],
        exposure_history=results['exposure_history']
    )
    
    # Print backtest results
    print_backtest_results(results) 