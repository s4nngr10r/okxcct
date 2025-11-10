# Usage Guide: okxauto

## Command-Line Options

### Basic Options
| Option         | Default   | Description                                 |
| -------------- | --------- | ------------------------------------------- |
| -margin-type   | MARGIN    | Margin instrument type (OKX API param)      |
| -swap-type     | SWAP      | Swap instrument type (OKX API param)        |
| -quote         | USDT      | Quote currency to filter instruments        |
| -timeout       | 30s       | HTTP timeout for API requests               |
| -top           | 10        | Number of top results to show               |
| -min-diff      | 0.24      | Minimum % mark price difference to include  |

### Order Book Analysis Options (use with -orderbook flag)
| Option           | Default | Description                                    |
| ---------------- | ------- | ---------------------------------------------- |
| -orderbook       | false   | Use order book data instead of mark prices    |
| -trade-size      | 1000.0  | Trade size in USD for order book analysis     |
| -min-liquidity   | 10000.0 | Minimum liquidity required in USD             |
| -max-slippage    | 0.5     | Maximum acceptable slippage in percentage     |
| -depth           | 20      | Order book depth to fetch                     |

## Example Commands

### Mark Price Analysis (Default)
```sh
# Default usage with mark prices
./getinsts

# Show top 5 symbols with at least 0.2% mark price diff
./getinsts -top 5 -min-diff 0.2

# Use a different quote currency (e.g., BTC)
./getinsts -quote BTC
```

### Order Book Analysis (Real Execution Prices)
```sh
# Use order book analysis for real execution prices
./getinsts -orderbook

# Custom trade size and liquidity requirements
./getinsts -orderbook -trade-size 5000 -min-liquidity 50000 -max-slippage 0.3

# Conservative settings for larger trades
./getinsts -orderbook -trade-size 10000 -min-liquidity 100000 -max-slippage 0.2 -depth 50

# Quick analysis with smaller trade size
./getinsts -orderbook -trade-size 500 -min-liquidity 5000 -top 5
```

## Analysis Modes

### 1. Mark Price Analysis (Default)
- Uses theoretical mark prices from OKX
- Faster execution, less API calls
- Good for initial screening and research
- **Limitation**: Doesn't account for real execution costs

### 2. Order Book Analysis (-orderbook flag)
- Fetches actual order book data
- Calculates weighted average prices based on trade size
- Includes liquidity checks and slippage analysis
- **Advantage**: Shows real executable prices and costs

## Output Formats

### Mark Price Analysis Output
```
Symbol      Margin        Swap          Actual Diff      % Diff    Structure    FundingRate  TimeToFunding  Fees     ActualProfit
BTC         43250.123456  43350.123456  +100.000000      0.23%     Contango     0.000100     2h30m          0.15%    0.08%
```

### Order Book Analysis Output
```
Symbol      MarginBuy     MarginSell    SwapBuy         SwapSell        % Diff    Structure    FundingRate  TimeToFunding  Fees     ActualProfit  Slippage
BTC         43255.123456  43245.123456  43355.123456    43345.123456    0.23%     Contango     0.000100     2h30m          0.15%    0.08%          0.023%
```

## Understanding Order Book Analysis

### Weighted Average Price
The tool calculates the weighted average price you would actually pay/receive for your trade size by:
1. Starting from the best price (top of order book)
2. Filling your order through multiple price levels
3. Calculating the average price weighted by the size filled at each level

### Liquidity Checks
- Verifies sufficient order book depth for your trade size
- Skips symbols with insufficient liquidity
- Shows total available liquidity in USD

### Slippage Analysis
- Calculates the difference between best price and weighted average price
- Filters out opportunities with excessive slippage
- Shows average slippage across both legs of the trade

## Best Practices

### For Research and Screening
```sh
# Use mark price analysis for quick screening
./getinsts -top 20 -min-diff 0.1
```

### For Real Trading Preparation
```sh
# Use order book analysis with realistic trade sizes
./getinsts -orderbook -trade-size 1000 -min-liquidity 10000 -max-slippage 0.5
```

### For Large Trades
```sh
# Conservative settings for larger positions
./getinsts -orderbook -trade-size 10000 -min-liquidity 100000 -max-slippage 0.2 -depth 50
```

## Troubleshooting
- **API Rate Limits**: Order book analysis makes more API calls, may hit rate limits
- **Insufficient Liquidity**: Increase `-min-liquidity` or decrease `-trade-size`
- **High Slippage**: Decrease `-trade-size` or increase `-max-slippage`
- **No Results**: Try decreasing `-min-diff` or adjusting liquidity parameters 