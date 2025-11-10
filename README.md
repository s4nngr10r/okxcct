# Cash-and-Carry Arbitrage Analyzer

A pet project exploring cash-and-carry arbitrage opportunities between spot and futures markets on OKX exchange. This project tests the theory that price differences between spot and perpetual futures markets can be exploited for arbitrage trading.

## Overview

This project consists of multiple tools for analyzing and trading cash-and-carry arbitrage:

1. **Python Analysis Tools**: Historical data analysis and visualization
2. **Go CLI Tool**: Real-time instrument analysis and opportunity detection
3. **Live Trading System**: Automated trading system (demo mode)

## Features

### Analysis Tools
- **Historical Analysis**: Plot and analyze price differences between spot and futures markets
- **Visualization**: Generate charts showing arbitrage opportunities over time
- **Data Fetching**: Download historical OHLCV data from OKX exchange
- **Cross-Exchange Comparison**: Compare perpetual futures prices across multiple exchanges

### Real-Time Analysis (Go)
- **Instrument Discovery**: Find matching spot and futures instruments
- **Order Book Analysis**: Calculate real execution prices with slippage
- **Funding Rate Integration**: Account for funding costs in arbitrage calculations
- **Fee Estimation**: Calculate total trading costs including fees and borrowing costs

### Live Trading System (Python)
- **Automated Trading**: Execute cash-and-carry arbitrage trades automatically
- **Risk Management**: Position limits, health checks, and emergency shutdown
- **Liquidity Analysis**: Order book depth and slippage tolerance checks
- **Margin Management**: Automatic borrowing and repayment for spot positions

## Project Structure

```
.
├── cash_and_carry_analyzer.py  # Historical data analysis and visualization
├── fetcher.py                   # OHLCV data fetcher from OKX
├── futcompare.py                # Cross-exchange perpetual futures comparison
├── live.py                      # Live trading system (demo mode)
├── okxauto/                     # Go CLI tool for real-time analysis
│   ├── cmd/
│   │   └── getinsts.go         # Main CLI entry point
│   ├── internal/               # Internal packages
│   └── docs/                   # Go tool documentation
├── requirements.txt            # Python dependencies (analysis tools)
└── requirements_live.txt       # Python dependencies (live trading)
```

## Installation

### Python Tools

1. Install dependencies for analysis tools:
```bash
pip install -r requirements.txt
```

2. For live trading system:
```bash
pip install -r requirements_live.txt
```

### Go CLI Tool

1. Navigate to the `okxauto` directory:
```bash
cd okxauto
```

2. Build the tool:
```bash
go build -o getinsts ./cmd/getinsts.go
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (see `.env.example` for template):

```bash
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_API_PASSPHRASE=your_api_passphrase_here
```

**Note**: For demo/testing purposes, these can be left empty. Never commit your actual `.env` file to version control!

Get your API credentials from: https://www.okx.com/account/my-api

## Usage

### Historical Analysis

Analyze historical price differences between spot and futures:

```bash
python cash_and_carry_analyzer.py spot_file.csv futures_file.csv --threshold 0.2
```

This will:
- Plot both price series
- Calculate symmetric percentage differences
- Show threshold lines for potentially profitable trades
- Generate statistics on arbitrage opportunities

### Fetch Historical Data

Download OHLCV data from OKX:

```bash
# Fetch spot data
python fetcher.py --symbol BTC/USDT --market-type spot --start-date 2024-01-01 --end-date 2024-01-31

# Fetch futures data
python fetcher.py --symbol BTC/USDT --market-type swap --start-date 2024-01-01 --end-date 2024-01-31
```

### Real-Time Analysis (Go CLI)

Find arbitrage opportunities using mark prices:

```bash
cd okxauto
./getinsts --top 10 --min-diff 0.24
```

Use order book analysis for real execution prices:

```bash
./getinsts --orderbook --trade-size 1000 --min-liquidity 10000 --max-slippage 0.5
```

### Cross-Exchange Comparison

Compare perpetual futures prices across Binance, Bybit, and MEXC:

```bash
python futcompare.py
```

### Live Trading System

**⚠️ WARNING: This is for educational purposes only. Use demo mode for testing.**

```bash
python live.py
```

The system runs in demo mode by default. Modify the configuration in `live.py` to customize trading parameters.

## Trading Strategy

### Cash-and-Carry Arbitrage

The strategy exploits price differences between spot and futures markets:

- **Contango**: When futures price > spot price
  - Trade: Long spot + Short futures
- **Backwardation**: When spot price > futures price
  - Trade: Short spot + Long futures

### Entry/Exit Conditions

- **Entry**: Price difference exceeds threshold (accounts for fees and costs)
- **Exit**: Price difference converges below exit threshold
- **Risk Management**: Position limits, liquidity checks, health monitoring

## Theory Being Tested

This project tests the hypothesis that:
1. Price differences between spot and perpetual futures markets are frequent enough to be exploitable
2. After accounting for fees, funding rates, and borrowing costs, profitable opportunities exist
3. Order book depth and liquidity are sufficient for execution at calculated prices
4. Automated systems can capture these opportunities faster than manual trading

## Disclaimer

**This software is for educational and research purposes only.**

- Trading cryptocurrencies involves substantial risk of loss
- Past performance does not guarantee future results
- Always test thoroughly in demo mode before using real funds
- The authors are not responsible for any financial losses
- This is a pet project to test a theory, not production-ready trading software

## Requirements

### Python
- Python 3.7+
- See `requirements.txt` and `requirements_live.txt` for dependencies

### Go
- Go 1.23+

## Contributing

This is a personal pet project, but suggestions and feedback are welcome!

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- OKX Exchange for providing API access
- CCXT library for exchange integration
- The crypto trading community for inspiration
