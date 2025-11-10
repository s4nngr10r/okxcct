import ccxt
from operator import itemgetter
import re

def normalize_symbol(symbol):
    # Remove /, :, and trailing contract info, e.g. BTC/USDT:USDT -> BTCUSDT
    symbol = symbol.replace('/', '').replace(':USDT', '').replace(':USD', '').replace(':', '')
    # Remove trailing -PERP, _PERP, etc.
    symbol = re.sub(r'[-_]PERP$', '', symbol)
    return symbol.upper()

def fetch_binance_perps():
    exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    markets = exchange.load_markets()
    perps = {normalize_symbol(symbol): symbol for symbol, market in markets.items() if market.get("swap") and market.get("contract") and not market.get("future")}
    tickers = exchange.fetch_tickers()
    return {
        norm: float(tickers[sym]["last"])
        for norm, sym in perps.items()
        if sym in tickers and tickers[sym]["last"] is not None
    }

def fetch_bybit_perps():
    exchange = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "future"}})
    markets = exchange.load_markets()
    perps = {normalize_symbol(symbol): symbol for symbol, market in markets.items() if market.get("swap") and market.get("contract") and not market.get("future")}
    tickers = exchange.fetch_tickers()
    return {
        norm: float(tickers[sym]["last"])
        for norm, sym in perps.items()
        if sym in tickers and tickers[sym]["last"] is not None
    }

def fetch_mexc_perps():
    exchange = ccxt.mexc({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    markets = exchange.load_markets()
    perps = {normalize_symbol(symbol): symbol for symbol, market in markets.items() if market.get("type") == "swap"}
    tickers = exchange.fetch_tickers()
    return {
        norm: float(tickers[sym]["last"])
        for norm, sym in perps.items()
        if sym in tickers and tickers[sym]["last"] is not None
    }

def main():
    print("Fetching perpetual futures prices from Binance, Bybit, and MEXC...")
    binance = fetch_binance_perps()
    bybit = fetch_bybit_perps()
    mexc = fetch_mexc_perps()

    print(f"Fetched {len(binance)} Binance perps: {list(binance.keys())[:5]} ...")
    print(f"Fetched {len(bybit)} Bybit perps: {list(bybit.keys())[:5]} ...")
    print(f"Fetched {len(mexc)} MEXC perps: {list(mexc.keys())[:5]} ...")

    # Build a symbol->exchange->price map
    all_symbols = set(binance.keys()) | set(bybit.keys()) | set(mexc.keys())
    symbol_prices = {}
    for symbol in all_symbols:
        symbol_prices[symbol] = {}
        if symbol in binance:
            symbol_prices[symbol]['Binance'] = binance[symbol]
        if symbol in bybit:
            symbol_prices[symbol]['Bybit'] = bybit[symbol]
        if symbol in mexc:
            symbol_prices[symbol]['MEXC'] = mexc[symbol]

    # For each symbol present on at least 2 exchanges, compare min/max
    results = []
    for symbol, prices in symbol_prices.items():
        if len(prices) < 2:
            continue
        min_exch = min(prices, key=prices.get)
        max_exch = max(prices, key=prices.get)
        min_price = prices[min_exch]
        max_price = prices[max_exch]
        diff = max_price - min_price
        avg = sum(prices.values()) / len(prices)
        percent_diff = 100 * diff / avg if avg else 0
        results.append({
            "symbol": symbol,
            "min_exch": min_exch,
            "min_price": min_price,
            "max_exch": max_exch,
            "max_price": max_price,
            "abs_diff": diff,
            "percent_diff": percent_diff,
            "all_prices": prices
        })

    results.sort(key=itemgetter("percent_diff"), reverse=True)
    print(f"\nTop 10 perpetual futures price differences across Binance, Bybit, MEXC (any 2+ exchanges):")
    print(f"{'Symbol':<12} {'MinExch':<8} {'MinPrice':<12} {'MaxExch':<8} {'MaxPrice':<12} {'AbsDiff':<12} {'%Diff':<8}")
    print("-"*80)
    for row in results[:10]:
        print(f"{row['symbol']:<12} {row['min_exch']:<8} {row['min_price']:<12.6f} {row['max_exch']:<8} {row['max_price']:<12.6f} {row['abs_diff']:<12.6f} {row['percent_diff']:<8.4f}")

if __name__ == "__main__":
    import sys
    if sys.version_info < (3, 7):
        print("This script requires Python 3.7+")
        sys.exit(1)
    main() 