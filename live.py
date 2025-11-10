import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import websockets
import aiohttp
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import hmac
import hashlib
import base64

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('live_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PositionType(Enum):
    NONE = "none"
    CONTANGO = "contango"  # Long spot, short futures
    BACKWARDATION = "backwardation"  # Short spot, long futures

@dataclass
class TradingConfig:
    """Configuration for trading parameters"""
    entrance_threshold: float = 0.3  # % difference to enter trade
    exit_threshold: float = 0.1      # % difference to exit trade
    max_positions: int = 5           # Maximum concurrent positions
    capital_per_trade: float = 1000  # Capital allocated per trade
    leverage: int = 10               # Leverage for both spot and futures
    min_liquidity_usd: float = 10000 # Minimum liquidity requirement
    max_slippage: float = 0.05       # Maximum slippage tolerance (%)
    funding_buffer_hours: int = 1    # Hours before funding to avoid trading
    health_check_interval: int = 30  # Seconds between health checks
    order_timeout: int = 10          # Seconds to wait for order execution

@dataclass
class SymbolInfo:
    """Information about a trading symbol"""
    symbol: str
    spot_symbol: str
    futures_symbol: str
    base_currency: str
    quote_currency: str
    min_order_size: float
    price_precision: int
    quantity_precision: int
    is_active: bool = True

@dataclass
class Position:
    """Represents an active arbitrage position"""
    symbol: str
    type: PositionType
    entry_time: datetime
    entry_spot_price: float
    entry_futures_price: float
    spot_order_id: str
    futures_order_id: str
    spot_quantity: float
    futures_quantity: float
    borrowed_amount: float = 0.0
    borrowed_currency: str = ""
    current_pnl: float = 0.0
    unrealized_pnl: float = 0.0

class OKXLiveTrader:
    def __init__(self, config: TradingConfig, api_key: str = "", secret_key: str = "", passphrase: str = ""):
        self.config = config
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = "https://www.okx.com"
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.demo_mode = True
        
        # State management
        self.symbols: Dict[str, SymbolInfo] = {}
        self.positions: Dict[str, Position] = {}
        self.account_balances = {}
        self.borrowed_balances = {}  # Track borrowed amounts
        self.total_pnl = 0.0  # Total realized PnL
        self.unrealized_pnl = 0.0  # Current unrealized PnL
        self.is_running = False
        self.last_health_check = time.time()
        
        # WebSocket connections
        self.websocket_connections = {}  # Store active WebSocket connections
        self.websocket_tasks = {}  # Store WebSocket tasks for cleanup
        self.price_data = {}  # Real-time price data
        
        # Trading symbols management
        self.top_liquid_symbols = []  # Top-50 most liquid symbols for active trading
        
        # Data storage
        self.funding_rates: Dict[str, float] = {}
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connections = {}
        
    async def initialize(self):
        """Initialize the trading system"""
        logger.info("Initializing OKX Live Trader...")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession()
        
        # Test API connection first
        api_ok = await self.test_api_connection()
        if not api_ok:
            logger.warning("API connection test failed, will use fallback symbols")
        
        # Get account information
        await self.get_account_info()
        
        # Get available symbols with initial price and liquidity data
        trading_pairs = await self.get_trading_symbols()
        
        # Populate symbols dictionary and store initial price data
        for pair in trading_pairs:
            symbol_key = f"{pair['base_currency']}-{pair['quote_currency']}"
            self.symbols[symbol_key] = SymbolInfo(
                symbol=symbol_key,
                spot_symbol=pair['spot_symbol'],
                futures_symbol=pair['futures_symbol'],
                base_currency=pair['base_currency'],
                quote_currency=pair['quote_currency'],
                min_order_size=0.001,  # Default values
                price_precision=8,
                quantity_precision=8,
                is_active=True
            )
            
            # Store initial price data from ticker response
            self.price_data[symbol_key] = {
                'spot': {
                    'price': pair.get('spot_price', 0.0),
                    'timestamp': time.time(),
                    'symbol': pair['spot_symbol'],
                    'volume_24h': pair.get('spot_volume_24h', 0.0)
                },
                'futures': {
                    'price': pair.get('futures_price', 0.0),
                    'timestamp': time.time(),
                    'symbol': pair['futures_symbol'],
                    'volume_24h': pair.get('futures_volume_24h', 0.0)
                },
                'liquidity_score': pair.get('liquidity_score', 0.0)
            }
        
        logger.info(f"Loaded {len(self.symbols)} trading symbol pairs")
        
        # Create list of top-50 most liquid symbols for active trading
        self.top_liquid_symbols = []
        sorted_symbols = sorted(
            self.symbols.keys(),
            key=lambda s: self.price_data[s]['liquidity_score'],
            reverse=True
        )
        self.top_liquid_symbols = sorted_symbols[:50]
        
        logger.info(f"Top 50 most liquid symbols for active trading:")
        for i, symbol in enumerate(self.top_liquid_symbols):
            liquidity = self.price_data[symbol]['liquidity_score']
            spot_price = self.price_data[symbol]['spot']['price']
            futures_price = self.price_data[symbol]['futures']['price']
            logger.info(f"{i+1:2d}. {symbol}: ${liquidity:,.0f} (Spot: ${spot_price:.4f}, Futures: ${futures_price:.4f})")
        
        # Initialize WebSocket connections
        await self.initialize_websockets()
        
        # Start background tasks
        asyncio.create_task(self.health_check_loop())
        asyncio.create_task(self.funding_rate_monitor())
        
        logger.info("Initialization complete")
    
    async def get_account_info(self):
        """Get account information and balances"""
        try:
            # For demo mode, we'll use mock data
            if self.demo_mode:
                self.account_balances = {
                    'USDT': 100000.0,
                    'BTC': 0.0,
                    'ETH': 0.0
                }
                self.borrowed_balances = {
                    'USDT': 0.0,
                    'BTC': 0.0,
                    'ETH': 0.0
                }
                logger.info("Demo mode: Using mock account balances")
            else:
                # Real API call would go here
                pass
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            raise
    
    async def get_trading_symbols(self):
        """Get all available trading symbols from OKX API and rank by liquidity"""
        try:
            if self.demo_mode:
                # For demo mode, fetch real symbols but use mock data for trading
                logger.info("Demo mode: Fetching real symbols from OKX API")
            
            # Fetch spot tickers (contains price and volume data)
            spot_tickers = await self.fetch_spot_symbols()
            
            # Fetch futures tickers (contains price and volume data)
            futures_tickers = await self.fetch_futures_symbols()
            
            # Filter for USDT pairs only
            usdt_spot_tickers = [s for s in spot_tickers if s['instId'].endswith('-USDT')]
            usdt_futures_tickers = [s for s in futures_tickers if s['instId'].endswith('-USDT-SWAP')]
            
            logger.info(f"Found {len(usdt_spot_tickers)} USDT spot tickers")
            logger.info(f"Found {len(usdt_futures_tickers)} USDT futures tickers")
            
            # Match spot and futures symbols and calculate liquidity scores
            trading_pairs = []
            
            for spot_ticker in usdt_spot_tickers:
                spot_inst_id = spot_ticker['instId']
                spot_base = spot_inst_id.replace('-USDT', '')
                
                # Find matching futures ticker
                matching_futures = None
                for futures_ticker in usdt_futures_tickers:
                    futures_inst_id = futures_ticker['instId']
                    if futures_inst_id == f"{spot_base}-USDT-SWAP":
                        matching_futures = futures_ticker
                        break
                
                if matching_futures:
                    # Extract price and volume data
                    spot_price = float(spot_ticker.get('last', 0))
                    spot_volume_24h = float(spot_ticker.get('vol24h', 0))
                    futures_price = float(matching_futures.get('last', 0))
                    futures_volume_24h = float(matching_futures.get('vol24h', 0))
                    
                    # Calculate liquidity score (24h volume in USD)
                    spot_liquidity_usd = spot_volume_24h * spot_price
                    futures_liquidity_usd = futures_volume_24h * futures_price
                    total_liquidity_usd = spot_liquidity_usd + futures_liquidity_usd
                    
                    trading_pairs.append({
                        'spot_symbol': spot_inst_id,
                        'futures_symbol': matching_futures['instId'],
                        'base_currency': spot_base,
                        'quote_currency': 'USDT',
                        'spot_price': spot_price,
                        'futures_price': futures_price,
                        'spot_volume_24h': spot_volume_24h,
                        'futures_volume_24h': futures_volume_24h,
                        'total_liquidity_usd': total_liquidity_usd,
                        'liquidity_score': total_liquidity_usd
                    })
                    
                    logger.debug(f"Matched {spot_base}-USDT: Spot=${spot_price:.4f}, Futures=${futures_price:.4f}, Liquidity=${total_liquidity_usd:,.0f}")
                else:
                    logger.warning(f"No futures match found for spot symbol: {spot_inst_id}")
            
            logger.info(f"Found {len(trading_pairs)} matching trading pairs")
            
            if not trading_pairs:
                logger.warning("No trading pairs found! Using fallback symbols...")
                # Fallback to predefined symbols
                trading_pairs = [
                    {'spot_symbol': 'BTC-USDT', 'futures_symbol': 'BTC-USDT-SWAP', 'base_currency': 'BTC', 'quote_currency': 'USDT', 'liquidity_score': 1000000},
                    {'spot_symbol': 'ETH-USDT', 'futures_symbol': 'ETH-USDT-SWAP', 'base_currency': 'ETH', 'quote_currency': 'USDT', 'liquidity_score': 800000},
                    {'spot_symbol': 'SOL-USDT', 'futures_symbol': 'SOL-USDT-SWAP', 'base_currency': 'SOL', 'quote_currency': 'USDT', 'liquidity_score': 600000},
                ]
            
            # Sort by liquidity score (highest first)
            trading_pairs.sort(key=lambda x: x['liquidity_score'], reverse=True)
            
            # Log top 20 most liquid symbols
            logger.info("Top 20 most liquid symbols:")
            for i, pair in enumerate(trading_pairs[:20]):
                logger.info(f"{i+1:2d}. {pair['base_currency']}-USDT: ${pair['liquidity_score']:,.0f} (Spot: ${pair.get('spot_price', 0):.4f}, Futures: ${pair.get('futures_price', 0):.4f})")
            
            return trading_pairs
            
        except Exception as e:
            logger.error(f"Error getting trading symbols: {e}")
            logger.exception("Full exception details:")
            # Return fallback symbols
            return [
                {'spot_symbol': 'BTC-USDT', 'futures_symbol': 'BTC-USDT-SWAP', 'base_currency': 'BTC', 'quote_currency': 'USDT', 'liquidity_score': 1000000},
                {'spot_symbol': 'ETH-USDT', 'futures_symbol': 'ETH-USDT-SWAP', 'base_currency': 'ETH', 'quote_currency': 'USDT', 'liquidity_score': 800000},
                {'spot_symbol': 'SOL-USDT', 'futures_symbol': 'SOL-USDT-SWAP', 'base_currency': 'SOL', 'quote_currency': 'USDT', 'liquidity_score': 600000},
            ]
    
    async def fetch_spot_symbols(self) -> List[Dict]:
        """Fetch spot trading symbols with ticker data from OKX API"""
        try:
            url = f"{self.base_url}/api/v5/market/tickers"
            params = {
                'instType': 'SPOT'
            }
            
            logger.info(f"Fetching spot tickers from: {url}")
            logger.info(f"Parameters: {params}")
            
            async with self.session.get(url, params=params) as response:
                logger.info(f"Spot API response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Spot API response code: {data.get('code')}")
                    
                    if data.get('code') == '0':
                        tickers = data.get('data', [])
                        logger.info(f"Successfully fetched {len(tickers)} spot tickers")
                        return tickers
                    else:
                        logger.error(f"Spot API error: {data.get('msg', 'Unknown error')}")
                        return []
                else:
                    response_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {response.reason}")
                    logger.error(f"Response body: {response_text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to fetch spot tickers: {e}")
            logger.exception("Full exception details:")
            return []
    
    async def fetch_futures_symbols(self) -> List[Dict]:
        """Fetch futures trading symbols with ticker data from OKX API"""
        try:
            url = f"{self.base_url}/api/v5/market/tickers"
            params = {
                'instType': 'SWAP'
            }
            
            logger.info(f"Fetching futures tickers from: {url}")
            logger.info(f"Parameters: {params}")
            
            async with self.session.get(url, params=params) as response:
                logger.info(f"Futures API response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Futures API response code: {data.get('code')}")
                    
                    if data.get('code') == '0':
                        tickers = data.get('data', [])
                        logger.info(f"Successfully fetched {len(tickers)} futures tickers")
                        return tickers
                    else:
                        logger.error(f"Futures API error: {data.get('msg', 'Unknown error')}")
                        return []
                else:
                    response_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {response.reason}")
                    logger.error(f"Response body: {response_text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to fetch futures tickers: {e}")
            logger.exception("Full exception details:")
            return []
    
    async def test_api_connection(self):
        """Test API connection to OKX"""
        try:
            logger.info("Testing OKX API connection...")
            
            # Test basic API endpoint
            test_url = f"{self.base_url}/api/v5/public/time"
            logger.info(f"Testing endpoint: {test_url}")
            
            async with self.session.get(test_url) as response:
                logger.info(f"Test API response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Test API response: {data}")
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Test API failed: {response.status} - {response_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            logger.exception("Full exception details:")
            return False
    
    def _load_fallback_symbols(self):
        """Load fallback symbols if API fails"""
        logger.warning("Using fallback symbol list due to API failure")
        fallback_symbols = [
            {'symbol': 'BTC-USDT', 'spot': 'BTC-USDT', 'futures': 'BTC-USDT-SWAP'},
            {'symbol': 'ETH-USDT', 'spot': 'ETH-USDT', 'futures': 'ETH-USDT-SWAP'},
            {'symbol': 'SOL-USDT', 'spot': 'SOL-USDT', 'futures': 'SOL-USDT-SWAP'},
            {'symbol': 'ADA-USDT', 'spot': 'ADA-USDT', 'futures': 'ADA-USDT-SWAP'},
        ]
        
        for sym in fallback_symbols:
            self.symbols[sym['symbol']] = SymbolInfo(
                symbol=sym['symbol'],
                spot_symbol=sym['spot'],
                futures_symbol=sym['futures'],
                base_currency=sym['symbol'].split('-')[0],
                quote_currency=sym['symbol'].split('-')[1],
                min_order_size=0.001 if 'BTC' in sym['symbol'] else 0.1,
                price_precision=2,
                quantity_precision=4,
                is_active=True
            )
    
    async def initialize_websockets(self):
        """Initialize price data and WebSocket connections for active positions only"""
        logger.info("Initializing price data...")
        
        # Price data is already initialized in the initialize() method from ticker responses
        logger.info(f"Price data initialized for {len(self.price_data)} symbols")
        
        # Log initial price data for top symbols
        logger.info("Initial price data for top 10 symbols:")
        for i, symbol in enumerate(self.top_liquid_symbols[:10]):
            spot_price = self.price_data[symbol]['spot']['price']
            futures_price = self.price_data[symbol]['futures']['price']
            liquidity = self.price_data[symbol]['liquidity_score']
            logger.info(f"{i+1:2d}. {symbol}: Spot=${spot_price:.4f}, Futures=${futures_price:.4f}, Liquidity=${liquidity:,.0f}")
        
        logger.info("Price data initialization complete")
    
    async def update_all_prices_via_rest(self):
        """Update prices for top-50 liquid symbols via REST API calls"""
        logger.info("Updating prices via REST API for top-50 liquid symbols...")
        
        # Use top-50 most liquid symbols for active trading
        symbols_to_update = []
        for symbol in self.top_liquid_symbols:
            if symbol in self.symbols:
                symbol_info = self.symbols[symbol]
                symbols_to_update.append(symbol_info)
                logger.debug(f"Updating: {symbol} -> Spot: {symbol_info.spot_symbol}, Futures: {symbol_info.futures_symbol}")
        
        logger.info(f"Updating {len(symbols_to_update)} top liquid symbols out of {len(self.symbols)} total")
        
        # Process symbols with conservative rate limiting
        batch_size = 2  # Process only 2 symbols at a time
        semaphore = asyncio.Semaphore(1)  # Max 1 concurrent request
        
        async def update_with_semaphore(symbol_info):
            async with semaphore:
                return await self.update_symbol_prices_via_rest(symbol_info.symbol, symbol_info)
        
        for i in range(0, len(symbols_to_update), batch_size):
            batch = symbols_to_update[i:i + batch_size]
            
            # Create tasks for this batch
            tasks = []
            for symbol_info in batch:
                tasks.append(update_with_semaphore(symbol_info))
            
            # Execute batch
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Conservative rate limiting
            if i + batch_size < len(symbols_to_update):
                await asyncio.sleep(2)  # Wait 2 seconds between batches
        
        logger.info("REST API price update complete")
    
    async def update_symbol_prices_via_rest(self, symbol: str, symbol_info: SymbolInfo):
        """Update prices for a single symbol via REST API"""
        try:
            # Get spot ticker
            spot_url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol_info.spot_symbol}"
            async with self.session.get(spot_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data') and len(data['data']) > 0:
                        ticker_data = data['data'][0]
                        if 'last' in ticker_data:
                            price = float(ticker_data['last'])
                            self.price_data[symbol]['spot']['price'] = price
                            self.price_data[symbol]['spot']['timestamp'] = time.time()
                        else:
                            logger.warning(f"No 'last' price in spot ticker for {symbol}: {ticker_data}")
                    else:
                        logger.warning(f"Invalid spot API response for {symbol}: {data}")
                else:
                    logger.warning(f"Spot API request failed for {symbol}: {response.status}")
            
            # Get futures ticker
            futures_url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol_info.futures_symbol}"
            async with self.session.get(futures_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data') and len(data['data']) > 0:
                        ticker_data = data['data'][0]
                        if 'last' in ticker_data:
                            price = float(ticker_data['last'])
                            self.price_data[symbol]['futures']['price'] = price
                            self.price_data[symbol]['futures']['timestamp'] = time.time()
                        else:
                            logger.warning(f"No 'last' price in futures ticker for {symbol}: {ticker_data}")
                    else:
                        logger.warning(f"Invalid futures API response for {symbol}: {data}")
                else:
                    logger.warning(f"Futures API request failed for {symbol}: {response.status}")
                            
        except Exception as e:
            logger.error(f"Failed to update prices for {symbol} via REST: {e}")
    
    async def start_websocket_for_position(self, symbol: str):
        """Start WebSocket connections for an active position"""
        if symbol not in self.symbols:
            return
        
        symbol_info = self.symbols[symbol]
        
        # Check if WebSocket is already running for this symbol
        if f"{symbol}_spot" in self.websocket_tasks or f"{symbol}_futures" in self.websocket_tasks:
            return
        
        logger.info(f"Starting WebSocket connections for active position: {symbol}")
        
        # OKX WebSocket URL
        ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        try:
            # Create WebSocket tasks for both spot and futures
            spot_task = asyncio.create_task(
                self.connect_spot_websocket(symbol, symbol_info.spot_symbol, ws_url)
            )
            futures_task = asyncio.create_task(
                self.connect_futures_websocket(symbol, symbol_info.futures_symbol, ws_url)
            )
            
            # Store tasks for cleanup
            self.websocket_tasks[f"{symbol}_spot"] = spot_task
            self.websocket_tasks[f"{symbol}_futures"] = futures_task
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket for {symbol}: {e}")
    
    async def stop_websocket_for_position(self, symbol: str):
        """Stop WebSocket connections for a closed position"""
        logger.info(f"Stopping WebSocket connections for closed position: {symbol}")
        
        # Cancel and remove spot WebSocket task
        spot_task_key = f"{symbol}_spot"
        if spot_task_key in self.websocket_tasks:
            task = self.websocket_tasks[spot_task_key]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.websocket_tasks[spot_task_key]
        
        # Cancel and remove futures WebSocket task
        futures_task_key = f"{symbol}_futures"
        if futures_task_key in self.websocket_tasks:
            task = self.websocket_tasks[futures_task_key]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.websocket_tasks[futures_task_key]
    
    async def connect_spot_websocket(self, symbol: str, spot_symbol: str, ws_url: str):
        """Connect to spot WebSocket for real-time price data"""
        while self.is_running:
            try:
                async with websockets.connect(ws_url) as websocket:
                    logger.info(f"Connected to spot WebSocket for {symbol}")
                    
                    # Subscribe to ticker channel
                    subscribe_message = {
                        "op": "subscribe",
                        "args": [
                            {
                                "channel": "tickers",
                                "instId": spot_symbol
                            }
                        ]
                    }
                    
                    await websocket.send(json.dumps(subscribe_message))
                    
                    # Listen for messages
                    async for message in websocket:
                        if not self.is_running:
                            break
                            
                        try:
                            data = json.loads(message)
                            
                            # Handle subscription confirmation
                            if 'event' in data and data['event'] == 'subscribe':
                                logger.info(f"Successfully subscribed to {symbol} spot ticker")
                                continue
                            
                            # Handle ticker data
                            if 'data' in data and len(data['data']) > 0:
                                ticker_data = data['data'][0]
                                if 'last' in ticker_data:
                                    price = float(ticker_data['last'])
                                    self.price_data[symbol]['spot']['price'] = price
                                    self.price_data[symbol]['spot']['timestamp'] = time.time()
                                    
                                    # Log price updates periodically
                                    if int(time.time()) % 30 == 0:  # Every 30 seconds
                                        logger.debug(f"{symbol} spot price: ${price:.4f}")
                                    
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON received from spot WebSocket for {symbol}")
                        except Exception as e:
                            logger.error(f"Error processing spot WebSocket message for {symbol}: {e}")
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Spot WebSocket connection closed for {symbol}, reconnecting...")
            except Exception as e:
                logger.error(f"Spot WebSocket error for {symbol}: {e}")
            
            # Wait before reconnecting
            if self.is_running:
                await asyncio.sleep(5)
    
    async def connect_futures_websocket(self, symbol: str, futures_symbol: str, ws_url: str):
        """Connect to futures WebSocket for real-time price data"""
        while self.is_running:
            try:
                async with websockets.connect(ws_url) as websocket:
                    logger.info(f"Connected to futures WebSocket for {symbol}")
                    
                    # Subscribe to ticker channel
                    subscribe_message = {
                        "op": "subscribe",
                        "args": [
                            {
                                "channel": "tickers",
                                "instId": futures_symbol
                            }
                        ]
                    }
                    
                    await websocket.send(json.dumps(subscribe_message))
                    
                    # Listen for messages
                    async for message in websocket:
                        if not self.is_running:
                            break
                            
                        try:
                            data = json.loads(message)
                            
                            # Handle subscription confirmation
                            if 'event' in data and data['event'] == 'subscribe':
                                logger.info(f"Successfully subscribed to {symbol} futures ticker")
                                continue
                            
                            # Handle ticker data
                            if 'data' in data and len(data['data']) > 0:
                                ticker_data = data['data'][0]
                                if 'last' in ticker_data:
                                    price = float(ticker_data['last'])
                                    self.price_data[symbol]['futures']['price'] = price
                                    self.price_data[symbol]['futures']['timestamp'] = time.time()
                                    
                                    # Log price updates periodically
                                    if int(time.time()) % 30 == 0:  # Every 30 seconds
                                        logger.debug(f"{symbol} futures price: ${price:.4f}")
                                    
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON received from futures WebSocket for {symbol}")
                        except Exception as e:
                            logger.error(f"Error processing futures WebSocket message for {symbol}: {e}")
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Futures WebSocket connection closed for {symbol}, reconnecting...")
            except Exception as e:
                logger.error(f"Futures WebSocket error for {symbol}: {e}")
            
            # Wait before reconnecting
            if self.is_running:
                await asyncio.sleep(5)
    
    async def simulate_price_feed(self, symbol: str):
        """Simulate real-time price feeds for demo mode"""
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 100
        volatility = 0.02
        
        while self.is_running:
            # Simulate price movements
            spot_change = np.random.normal(0, volatility)
            futures_change = np.random.normal(0, volatility)
            
            # Add some correlation but allow for arbitrage opportunities
            correlation = 0.95
            futures_change = correlation * spot_change + (1 - correlation) * np.random.normal(0, volatility)
            
            self.price_data[symbol]['spot']['price'] = base_price * (1 + spot_change)
            self.price_data[symbol]['futures']['price'] = base_price * (1 + futures_change)
            self.price_data[symbol]['spot']['timestamp'] = time.time()
            self.price_data[symbol]['futures']['timestamp'] = time.time()
            
            await asyncio.sleep(1)  # Update every second
    
    def calculate_percentage_difference(self, spot_price: float, futures_price: float) -> float:
        """Calculate symmetric percentage difference"""
        if spot_price == 0 or futures_price == 0:
            return 0.0
        return ((futures_price - spot_price) / ((futures_price + spot_price) / 2)) * 100
    
    async def get_order_book_via_rest(self, symbol: str, depth: int = 20) -> Dict:
        """Get order book data via REST API"""
        try:
            symbol_info = self.symbols[symbol]
            
            # Get spot order book
            spot_url = f"https://www.okx.com/api/v5/market/books?instId={symbol_info.spot_symbol}&sz={depth}"
            spot_book = {'bids': [], 'asks': []}
            
            async with self.session.get(spot_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data'):
                        book_data = data['data'][0]
                        spot_book['bids'] = [[float(price), float(size)] for price, size, *_ in book_data['bids']]
                        spot_book['asks'] = [[float(price), float(size)] for price, size, *_ in book_data['asks']]
            
            # Get futures order book
            futures_url = f"https://www.okx.com/api/v5/market/books?instId={symbol_info.futures_symbol}&sz={depth}"
            futures_book = {'bids': [], 'asks': []}
            
            async with self.session.get(futures_url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data'):
                        book_data = data['data'][0]
                        futures_book['bids'] = [[float(price), float(size)] for price, size, *_ in book_data['bids']]
                        futures_book['asks'] = [[float(price), float(size)] for price, size, *_ in book_data['asks']]
            
            return {
                'spot': spot_book,
                'futures': futures_book
            }
            
        except Exception as e:
            logger.error(f"Failed to get order book for {symbol}: {e}")
            return {'spot': {'bids': [], 'asks': []}, 'futures': {'bids': [], 'asks': []}}
    
    async def check_liquidity(self, symbol: str) -> bool:
        """Check if symbol has sufficient liquidity"""
        try:
            # Get order book data
            order_book = await self.get_order_book_via_rest(symbol, depth=10)
            
            # Calculate liquidity for spot
            spot_bid_liquidity = sum(size for _, size in order_book['spot']['bids'][:5])
            spot_ask_liquidity = sum(size for _, size in order_book['spot']['asks'][:5])
            
            # Calculate liquidity for futures
            futures_bid_liquidity = sum(size for _, size in order_book['futures']['bids'][:5])
            futures_ask_liquidity = sum(size for _, size in order_book['futures']['asks'][:5])
            
            # Get current prices
            spot_price = self.price_data[symbol]['spot']['price']
            futures_price = self.price_data[symbol]['futures']['price']
            
            # Calculate USD liquidity
            spot_bid_usd = spot_bid_liquidity * spot_price
            spot_ask_usd = spot_ask_liquidity * spot_price
            futures_bid_usd = futures_bid_liquidity * futures_price
            futures_ask_usd = futures_ask_liquidity * futures_price
            
            # Check if liquidity meets minimum requirement
            min_liquidity = self.config.min_liquidity_usd
            has_sufficient_liquidity = (
                spot_bid_usd >= min_liquidity and
                spot_ask_usd >= min_liquidity and
                futures_bid_usd >= min_liquidity and
                futures_ask_usd >= min_liquidity
            )
            
            if not has_sufficient_liquidity:
                logger.warning(f"Insufficient liquidity for {symbol}: Spot({spot_bid_usd:.0f}/{spot_ask_usd:.0f}) Futures({futures_bid_usd:.0f}/{futures_ask_usd:.0f}) USD")
            
            return has_sufficient_liquidity
            
        except Exception as e:
            logger.error(f"Failed to check liquidity for {symbol}: {e}")
            return False
    
    async def check_funding_rate(self, symbol: str) -> bool:
        """Check if we should avoid trading due to funding rates"""
        try:
            # For demo mode, assume funding is not an issue
            # In real implementation, would check funding rate and timing
            return True
        except Exception as e:
            logger.error(f"Failed to check funding rate for {symbol}: {e}")
            return False
    
    async def place_order(self, symbol: str, side: str, order_type: str, 
                         quantity: float, price: float = None) -> str:
        """Place an order (simulated for demo mode)"""
        try:
            # Simulate order placement
            order_id = f"demo_order_{int(time.time() * 1000)}"
            
            # Get current market price for logging
            if price is None and order_type == 'market':
                price = "market"  # Default fallback
                for price_data in self.price_data.values():
                    spot = price_data.get('spot', {})
                    futures = price_data.get('futures', {})
                    spot_symbol = spot.get('symbol')
                    futures_symbol = futures.get('symbol')
                    if symbol == spot_symbol:
                        price = spot.get('price', "market")
                        break
                    elif symbol == futures_symbol:
                        price = futures.get('price', "market")
                        break
            
            logger.info(f"Placed {side} {order_type} order: {quantity} {symbol} @ {price}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    async def borrow_margin(self, currency: str, amount: float) -> bool:
        """Borrow funds for margin trading"""
        try:
            # Simulate margin borrowing
            if currency not in self.borrowed_balances:
                self.borrowed_balances[currency] = 0.0
            self.borrowed_balances[currency] += amount
            logger.info(f"Borrowed {amount} {currency} for margin trading")
            return True
        except Exception as e:
            logger.error(f"Failed to borrow margin: {e}")
            return False
    
    async def repay_margin(self, currency: str, amount: float) -> bool:
        """Repay borrowed margin funds"""
        try:
            # Simulate margin repayment
            if currency in self.borrowed_balances:
                self.borrowed_balances[currency] -= amount
                if self.borrowed_balances[currency] < 0:
                    self.borrowed_balances[currency] = 0.0
            logger.info(f"Repaid {amount} {currency} margin")
            return True
        except Exception as e:
            logger.error(f"Failed to repay margin: {e}")
            return False
    
    async def enter_position(self, symbol: str, position_type: PositionType) -> bool:
        """Enter a new arbitrage position"""
        try:
            symbol_info = self.symbols[symbol]
            spot_price = self.price_data[symbol]['spot']['price']
            futures_price = self.price_data[symbol]['futures']['price']
            
            # Calculate position sizes
            trade_value = self.config.capital_per_trade
            spot_quantity = (trade_value * 0.5) / spot_price
            futures_quantity = (trade_value * 0.5) / futures_price
            
            # Place orders
            if position_type == PositionType.CONTANGO:
                # Long spot, short futures
                spot_order_id = await self.place_order(symbol_info.spot_symbol, 'buy', 'market', spot_quantity)
                futures_order_id = await self.place_order(symbol_info.futures_symbol, 'sell', 'market', futures_quantity)
                
                # Borrow funds for spot position
                borrowed_amount = spot_quantity * spot_price
                await self.borrow_margin('USDT', borrowed_amount)
                
            else:  # BACKWARDATION
                # Short spot, long futures
                spot_order_id = await self.place_order(symbol_info.spot_symbol, 'sell', 'market', spot_quantity)
                futures_order_id = await self.place_order(symbol_info.futures_symbol, 'buy', 'market', futures_quantity)
                
                # Borrow the asset for shorting
                await self.borrow_margin(symbol_info.base_currency, spot_quantity)
                borrowed_amount = spot_quantity * spot_price
            
            # Create position record
            position = Position(
                symbol=symbol,
                type=position_type,
                entry_time=datetime.now(),
                entry_spot_price=spot_price,
                entry_futures_price=futures_price,
                spot_order_id=spot_order_id,
                futures_order_id=futures_order_id,
                spot_quantity=spot_quantity,
                futures_quantity=futures_quantity,
                borrowed_amount=borrowed_amount,
                borrowed_currency='USDT' if position_type == PositionType.CONTANGO else symbol_info.base_currency
            )
            
            self.positions[symbol] = position
            logger.info(f"Entered {position_type.value} position for {symbol}")
            
            # Start WebSocket connections for real-time price monitoring
            await self.start_websocket_for_position(symbol)
            
            # Display updated portfolio status
            self.display_portfolio_status()
            return True
            
        except Exception as e:
            logger.error(f"Failed to enter position for {symbol}: {e}")
            return False
    
    async def exit_position(self, symbol: str) -> bool:
        """Exit an existing position"""
        try:
            position = self.positions[symbol]
            symbol_info = self.symbols[symbol]
            
            current_spot_price = self.price_data[symbol]['spot']['price']
            current_futures_price = self.price_data[symbol]['futures']['price']
            
            # Close positions
            if position.type == PositionType.CONTANGO:
                # Sell spot, buy futures
                await self.place_order(symbol_info.spot_symbol, 'sell', 'market', position.spot_quantity)
                await self.place_order(symbol_info.futures_symbol, 'buy', 'market', position.futures_quantity)
                
                # Repay borrowed funds
                await self.repay_margin('USDT', position.borrowed_amount)
                
            else:  # BACKWARDATION
                # Buy spot, sell futures
                await self.place_order(symbol_info.spot_symbol, 'buy', 'market', position.spot_quantity)
                await self.place_order(symbol_info.futures_symbol, 'sell', 'market', position.futures_quantity)
                
                # Repay borrowed asset
                await self.repay_margin(symbol_info.base_currency, position.spot_quantity)
            
            # Calculate PnL
            spot_pnl = ((current_spot_price - position.entry_spot_price) / position.entry_spot_price) * position.spot_quantity * position.entry_spot_price
            futures_pnl = ((position.entry_futures_price - current_futures_price) / position.entry_futures_price) * position.futures_quantity * position.entry_futures_price
            
            if position.type == PositionType.BACKWARDATION:
                spot_pnl = -spot_pnl
                futures_pnl = -futures_pnl
            
            total_pnl = spot_pnl + futures_pnl
            
            # Update total realized PnL
            self.total_pnl += total_pnl
            
            logger.info(f"Exited position for {symbol}. PnL: ${total_pnl:.2f}")
            
            # Remove position
            del self.positions[symbol]
            
            # Stop WebSocket connections for this symbol
            await self.stop_websocket_for_position(symbol)
            
            # Display updated portfolio status
            self.display_portfolio_status()
            return True
            
        except Exception as e:
            logger.error(f"Failed to exit position for {symbol}: {e}")
            return False
    
    async def check_exit_conditions(self, symbol: str) -> bool:
        """Check if position should be exited"""
        if symbol not in self.positions:
            return False
        
        position = self.positions[symbol]
        current_spot_price = self.price_data[symbol]['spot']['price']
        current_futures_price = self.price_data[symbol]['futures']['price']
        
        pct_diff = self.calculate_percentage_difference(current_spot_price, current_futures_price)
        
        if position.type == PositionType.CONTANGO:
            return pct_diff < self.config.exit_threshold
        else:  # BACKWARDATION
            return pct_diff > -self.config.exit_threshold
    
    async def check_entry_conditions(self, symbol: str) -> Tuple[bool, PositionType]:
        """Check if we should enter a new position"""
        if symbol in self.positions:
            return False, PositionType.NONE
        
        if len(self.positions) >= self.config.max_positions:
            return False, PositionType.NONE
        
        current_spot_price = self.price_data[symbol]['spot']['price']
        current_futures_price = self.price_data[symbol]['futures']['price']
        
        if current_spot_price == 0 or current_futures_price == 0:
            return False, PositionType.NONE
        
        # Check liquidity before considering entry
        if not await self.check_liquidity(symbol):
            return False, PositionType.NONE
        
        pct_diff = self.calculate_percentage_difference(current_spot_price, current_futures_price)
        
        # Check entry conditions
        if pct_diff > self.config.entrance_threshold:
            return True, PositionType.CONTANGO
        elif pct_diff < -self.config.entrance_threshold:
            return True, PositionType.BACKWARDATION
        
        return False, PositionType.NONE
    
    async def health_check_loop(self):
        """Periodic health check loop"""
        while self.is_running:
            try:
                await self.perform_health_check()
                await asyncio.sleep(self.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                await asyncio.sleep(5)
    
    async def perform_health_check(self):
        """Perform comprehensive health check"""
        try:
            # Check account status
            await self.get_account_info()
            
            # Check API connectivity
            # In real implementation, would ping API endpoints
            
            # Check for unexpected balance changes
            # In real implementation, would compare with expected balances
            
            # Check position consistency
            # In real implementation, would verify all positions are still valid
            
            self.last_health_check = time.time()
            logger.debug("Health check completed successfully")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            # In real implementation, would trigger emergency shutdown
            await self.emergency_shutdown()
    
    async def emergency_shutdown(self):
        """Emergency shutdown - close all positions"""
        logger.warning("Emergency shutdown initiated")
        
        # Close all positions
        for symbol in list(self.positions.keys()):
            try:
                await self.exit_position(symbol)
            except Exception as e:
                logger.error(f"Failed to close position {symbol} during emergency shutdown: {e}")
        
        self.is_running = False
        logger.info("Emergency shutdown completed")
    
    async def funding_rate_monitor(self):
        """Monitor funding rates and avoid trading near funding times"""
        while self.is_running:
            try:
                # Check funding rates for all symbols
                for symbol in self.symbols:
                    # In real implementation, would fetch actual funding rates
                    # For demo mode, assume no funding rate issues
                    pass
                
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Funding rate monitor failed: {e}")
                await asyncio.sleep(30)
    
    async def trading_loop(self):
        """Main trading loop"""
        logger.info("Starting trading loop...")
        
        last_status_display = time.time()
        last_rest_update = time.time()
        status_interval = 30  # Display status every 30 seconds
        rest_update_interval = 60  # Update prices via REST every 60 seconds
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # Periodic REST API price updates for top-50 liquid symbols
                if current_time - last_rest_update >= rest_update_interval:
                    await self.update_all_prices_via_rest()
                    last_rest_update = current_time
                
                # Check for exit conditions on existing positions
                for symbol in list(self.positions.keys()):
                    if await self.check_exit_conditions(symbol):
                        await self.exit_position(symbol)
                
                # Check for new entry opportunities (only for top-50 liquid symbols with valid price data)
                for symbol in self.top_liquid_symbols:
                    if symbol in self.symbols and symbol in self.price_data and self.has_valid_price_data(symbol):
                        should_enter, position_type = await self.check_entry_conditions(symbol)
                        if should_enter:
                            await self.enter_position(symbol, position_type)
                
                # Display periodic status
                if current_time - last_status_display >= status_interval:
                    self.display_portfolio_status()
                    self.display_price_data_status()
                    last_status_display = current_time
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(5)
    
    async def start(self):
        """Start the live trading system"""
        try:
            logger.info("Starting OKX Live Trader...")
            
            await self.initialize()
            self.is_running = True
            
            # Start trading loop
            await self.trading_loop()
            
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        
        self.is_running = False
        
        # Close all positions
        for symbol in list(self.positions.keys()):
            try:
                await self.exit_position(symbol)
            except Exception as e:
                logger.error(f"Failed to close position {symbol} during shutdown: {e}")
        
        # Close WebSocket connections
        logger.info("Closing WebSocket connections...")
        for task_name, task in self.websocket_tasks.items():
            try:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                logger.info(f"Closed WebSocket task: {task_name}")
            except Exception as e:
                logger.error(f"Error closing WebSocket task {task_name}: {e}")
        
        # Close HTTP session
        if self.session:
            await self.session.close()
        
        logger.info("Shutdown complete")

    def calculate_portfolio_status(self):
        """Calculate current portfolio status and PnL"""
        total_unrealized_pnl = 0.0
        position_count = len(self.positions)
        
        for symbol, position in self.positions.items():
            if symbol in self.price_data:
                current_spot_price = self.price_data[symbol]['spot']['price']
                current_futures_price = self.price_data[symbol]['futures']['price']
                
                # Calculate unrealized PnL
                spot_pnl = ((current_spot_price - position.entry_spot_price) / position.entry_spot_price) * position.spot_quantity * position.entry_spot_price
                futures_pnl = ((position.entry_futures_price - current_futures_price) / position.entry_futures_price) * position.futures_quantity * position.entry_futures_price
                
                if position.type == PositionType.BACKWARDATION:
                    spot_pnl = -spot_pnl
                    futures_pnl = -futures_pnl
                
                position.unrealized_pnl = spot_pnl + futures_pnl
                total_unrealized_pnl += position.unrealized_pnl
        
        self.unrealized_pnl = total_unrealized_pnl
        return {
            'total_pnl': self.total_pnl,
            'unrealized_pnl': total_unrealized_pnl,
            'total_pnl_combined': self.total_pnl + total_unrealized_pnl,
            'position_count': position_count,
            'account_balances': self.account_balances.copy(),
            'borrowed_balances': self.borrowed_balances.copy()
        }
    
    def display_portfolio_status(self):
        """Display current portfolio status"""
        status = self.calculate_portfolio_status()
        
        logger.info("=" * 60)
        logger.info("PORTFOLIO STATUS")
        logger.info("=" * 60)
        logger.info(f"Active Positions: {status['position_count']}")
        logger.info(f"Realized PnL: ${status['total_pnl']:.2f}")
        logger.info(f"Unrealized PnL: ${status['unrealized_pnl']:.2f}")
        logger.info(f"Total PnL: ${status['total_pnl_combined']:.2f}")
        logger.info("-" * 40)
        logger.info("ACCOUNT BALANCES:")
        for currency, balance in status['account_balances'].items():
            if balance > 0:
                logger.info(f"  {currency}: {balance:.4f}")
        logger.info("-" * 40)
        logger.info("BORROWED BALANCES:")
        total_borrowed = 0
        for currency, borrowed in status['borrowed_balances'].items():
            if borrowed > 0:
                logger.info(f"  {currency}: {borrowed:.4f}")
                total_borrowed += borrowed
        if total_borrowed == 0:
            logger.info("  No borrowed funds")
        logger.info("=" * 60)

    def has_valid_price_data(self, symbol: str) -> bool:
        """Check if we have valid price data for a symbol"""
        if symbol not in self.price_data:
            return False
        
        spot_data = self.price_data[symbol]['spot']
        futures_data = self.price_data[symbol]['futures']
        
        # Check if we have recent prices (within last 30 seconds)
        current_time = time.time()
        spot_age = current_time - spot_data['timestamp']
        futures_age = current_time - futures_data['timestamp']
        
        # Prices should be recent and non-zero
        return (spot_data['price'] > 0 and 
                futures_data['price'] > 0 and 
                spot_age < 30 and 
                futures_age < 30)
    
    def get_price_data_status(self) -> Dict[str, Dict]:
        """Get status of price data for all symbols"""
        status = {}
        current_time = time.time()
        
        for symbol in self.symbols:
            if symbol in self.price_data:
                spot_data = self.price_data[symbol]['spot']
                futures_data = self.price_data[symbol]['futures']
                
                spot_age = current_time - spot_data['timestamp']
                futures_age = current_time - futures_data['timestamp']
                
                status[symbol] = {
                    'spot_price': spot_data['price'],
                    'futures_price': futures_data['price'],
                    'spot_age_seconds': spot_age,
                    'futures_age_seconds': futures_age,
                    'has_valid_data': self.has_valid_price_data(symbol)
                }
            else:
                status[symbol] = {
                    'spot_price': 0,
                    'futures_price': 0,
                    'spot_age_seconds': float('inf'),
                    'futures_age_seconds': float('inf'),
                    'has_valid_data': False
                }
        
        return status

    def display_price_data_status(self):
        """Display status of price data feeds"""
        status = self.get_price_data_status()
        
        logger.info("=" * 60)
        logger.info("PRICE DATA STATUS")
        logger.info("=" * 60)
        
        valid_count = 0
        total_count = len(status)
        
        for symbol, data in status.items():
            if data['has_valid_data']:
                valid_count += 1
                logger.info(f"{symbol}: ✅ Spot=${data['spot_price']:.4f} Futures=${data['futures_price']:.4f}")
            else:
                logger.warning(f"{symbol}: ❌ Spot=${data['spot_price']:.4f} Futures=${data['futures_price']:.4f} (Age: {data['spot_age_seconds']:.1f}s/{data['futures_age_seconds']:.1f}s)")
        
        logger.info(f"Price feeds: {valid_count}/{total_count} active")
        logger.info("=" * 60)

async def main():
    """Main entry point"""
    # Configuration
    config = TradingConfig(
        entrance_threshold=0.3,
        exit_threshold=0.1,
        max_positions=5,
        capital_per_trade=1000,
        leverage=10,
        min_liquidity_usd=10000,
        max_slippage=0.05,
        funding_buffer_hours=1,
        health_check_interval=30,
        order_timeout=10
    )
    
    # Create trader instance
    trader = OKXLiveTrader(config)
    
    # Start trading
    await trader.start()

if __name__ == "__main__":
    asyncio.run(main()) 