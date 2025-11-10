# OKX Live Cash-and-Carry Arbitrage Trader

A comprehensive live trading system for cash-and-carry arbitrage on OKX exchange using demo mode.

## Features

### Core Trading Logic
- **Cash-and-Carry Arbitrage**: Implements the same strategy from `cash_and_carry_analyzer.py`
- **Multi-Symbol Trading**: Automatically trades all available symbol pairs
- **Contango & Backwardation**: Supports both types of arbitrage opportunities
- **Real-time Monitoring**: Continuous price monitoring and opportunity detection

### Risk Management & Safety
- **Demo Mode Only**: All trades are paper trades for safety
- **Real-time Health Checks**: Monitors account status, API connectivity, and system health
- **Emergency Shutdown**: Immediately closes all positions on system anomalies
- **Position Limits**: Configurable maximum concurrent positions

### Liquidity & Execution
- **Order Book Analysis**: Checks bid/ask spreads and depth before trading
- **Liquidity Thresholds**: Only trades symbols with sufficient volume
- **Smart Order Placement**: Uses limit orders with slippage tolerance
- **Partial Fill Handling**: Manages incomplete order executions

### Funding & Margin Management
- **Automatic Margin Borrowing**: Borrows required funds for spot positions
- **Automatic Repayment**: Returns borrowed funds when positions close
- **Balance Monitoring**: Ensures spot and futures accounts are balanced
- **Funding Rate Avoidance**: Skips trades near funding payment times
- **Interest Tracking**: Accounts for borrowing costs in PnL calculations

## Installation

1. Install dependencies:
```bash
pip install -r requirements_live.txt
```

2. Configure your API credentials (for demo mode, these can be empty):
```python
# In live.py, modify the OKXLiveTrader initialization
trader = OKXLiveTrader(config, api_key="", secret_key="", passphrase="")
```

## Configuration

The `TradingConfig` class allows you to customize all trading parameters:

```python
config = TradingConfig(
    entrance_threshold=0.3,      # % difference to enter trade
    exit_threshold=0.1,          # % difference to exit trade
    max_positions=5,             # Maximum concurrent positions
    capital_per_trade=1000,      # Capital allocated per trade
    leverage=10,                 # Leverage for both spot and futures
    min_liquidity_usd=10000,     # Minimum liquidity requirement
    max_slippage=0.05,           # Maximum slippage tolerance (%)
    funding_buffer_hours=1,      # Hours before funding to avoid trading
    health_check_interval=30,    # Seconds between health checks
    order_timeout=10             # Seconds to wait for order execution
)
```

## Usage

### Basic Usage
```bash
python live.py
```

### Custom Configuration
Modify the `main()` function in `live.py` to adjust parameters:

```python
async def main():
    config = TradingConfig(
        entrance_threshold=0.5,    # More conservative entry
        exit_threshold=0.2,        # Earlier exit
        max_positions=3,           # Fewer concurrent positions
        capital_per_trade=500      # Smaller position sizes
    )
    
    trader = OKXLiveTrader(config)
    await trader.start()
```

## Trading Strategy

### Entry Conditions
- **Contango**: When futures price > spot price by entrance threshold
- **Backwardation**: When spot price > futures price by entrance threshold

### Position Management
- **Contango Trade**: Long spot + Short futures
- **Backwardation Trade**: Short spot + Long futures
- **Leverage**: 10x on both spot and futures legs
- **Position Sizing**: 10% of capital per leg (20% total per trade)

### Exit Conditions
- **Contango Exit**: When price difference falls below exit threshold
- **Backwardation Exit**: When price difference rises above negative exit threshold

## Safety Features

### Health Monitoring
- **Account Status**: Continuous monitoring of account balances
- **API Connectivity**: Regular API endpoint health checks
- **Position Consistency**: Verification that all positions are valid
- **Balance Changes**: Detection of unexpected balance movements

### Emergency Procedures
- **Automatic Shutdown**: Triggers on system anomalies
- **Position Closure**: Immediately closes all open positions
- **Error Recovery**: Graceful handling of network and API errors
- **Logging**: Comprehensive logging of all actions and errors

## Logging

The system provides comprehensive logging:
- **File Logging**: All events saved to `live_trading.log`
- **Console Output**: Real-time status updates
- **Trade Details**: Complete trade entry/exit information
- **Error Tracking**: Detailed error messages and stack traces

## Demo Mode Features

### Simulated Environment
- **Mock Account**: $100,000 starting balance
- **Simulated Prices**: Realistic price movements with correlation
- **Paper Trades**: No real money at risk
- **Realistic Fees**: Simulated trading fees and margin costs

### Available Symbols
- BTC-USDT
- ETH-USDT
- SOL-USDT
- ADA-USDT

## Production Considerations

### Before Going Live
1. **API Integration**: Replace simulated functions with real OKX API calls
2. **Risk Management**: Implement additional risk controls
3. **Monitoring**: Set up external monitoring and alerting
4. **Backup Systems**: Implement redundant systems and failover
5. **Compliance**: Ensure regulatory compliance for your jurisdiction

### Additional Features to Implement
- **Telegram/Discord Notifications**: Real-time trade alerts
- **Database Logging**: Persistent trade and performance data
- **Performance Analytics**: Real-time PnL and risk metrics
- **Portfolio Management**: Dynamic position sizing and allocation
- **Cross-Exchange Arbitrage**: Compare prices across multiple venues

## Disclaimer

This software is for educational and demonstration purposes only. Trading cryptocurrencies involves substantial risk of loss. Always test thoroughly in demo mode before using real funds. The authors are not responsible for any financial losses incurred through the use of this software.

## Support

For issues and questions:
1. Check the logs in `live_trading.log`
2. Review the configuration parameters
3. Ensure all dependencies are installed correctly
4. Verify API credentials and permissions (for live trading) 