package gookx

import (
	"encoding/json"
	"net/http"
	"time"
)

type Config struct {
	MarginInstType string
	SwapInstType   string
	QuoteCurrency  string
	HTTPTimeout    time.Duration
	UserAgent      string
	APIKey         string
	APISecret      string
	APIPassphrase  string
}

type OKXInstrumentResponse struct {
	Code string       `json:"code"`
	Msg  string       `json:"msg"`
	Data []Instrument `json:"data"`
}

type OKXMarkPriceResponse struct {
	Code string      `json:"code"`
	Msg  string      `json:"msg"`
	Data []MarkPrice `json:"data"`
}

type Instrument struct {
	InstID   string                 `json:"instId"`
	InstType string                 `json:"instType"`
	BaseCcy  string                 `json:"baseCcy"`
	QuoteCcy string                 `json:"quoteCcy"`
	State    string                 `json:"state"`
	MarkPx   string                 `json:"markPx"`
	Lever    string                 `json:"lever"`
	LotSz    string                 `json:"lotSz"`
	TickSz   string                 `json:"tickSz"`
	MinSz    string                 `json:"minSz"`
	MaxSz    string                 `json:"maxSz"`
	Extra    map[string]interface{} `json:"-"`
}

func (i *Instrument) UnmarshalJSON(data []byte) error {
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	if v, ok := raw["instId"].(string); ok {
		i.InstID = v
		delete(raw, "instId")
	}
	if v, ok := raw["instType"].(string); ok {
		i.InstType = v
		delete(raw, "instType")
	}
	if v, ok := raw["baseCcy"].(string); ok {
		i.BaseCcy = v
		delete(raw, "baseCcy")
	}
	if v, ok := raw["quoteCcy"].(string); ok {
		i.QuoteCcy = v
		delete(raw, "quoteCcy")
	}
	if v, ok := raw["state"].(string); ok {
		i.State = v
		delete(raw, "state")
	}
	if v, ok := raw["markPx"].(string); ok {
		i.MarkPx = v
		delete(raw, "markPx")
	}
	if v, ok := raw["lever"].(string); ok {
		i.Lever = v
		delete(raw, "lever")
	}
	if v, ok := raw["lotSz"].(string); ok {
		i.LotSz = v
		delete(raw, "lotSz")
	}
	if v, ok := raw["tickSz"].(string); ok {
		i.TickSz = v
		delete(raw, "tickSz")
	}
	if v, ok := raw["minSz"].(string); ok {
		i.MinSz = v
		delete(raw, "minSz")
	}
	if v, ok := raw["maxSz"].(string); ok {
		i.MaxSz = v
		delete(raw, "maxSz")
	}
	i.Extra = raw
	return nil
}

type MarkPrice struct {
	InstID string                 `json:"instId"`
	MarkPx string                 `json:"markPx"`
	TS     string                 `json:"ts"`
	Extra  map[string]interface{} `json:"-"`
}

func (m *MarkPrice) UnmarshalJSON(data []byte) error {
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	if v, ok := raw["instId"].(string); ok {
		m.InstID = v
		delete(raw, "instId")
	}
	if v, ok := raw["markPx"].(string); ok {
		m.MarkPx = v
		delete(raw, "markPx")
	}
	if v, ok := raw["ts"].(string); ok {
		m.TS = v
		delete(raw, "ts")
	}
	m.Extra = raw
	return nil
}

type MatchingSymbol struct {
	BaseSymbol string     `json:"baseSymbol"`
	Margin     Instrument `json:"margin"`
	Swap       Instrument `json:"swap"`
}

type DiffResult struct {
	BaseSymbol    string  `json:"baseSymbol"`
	MarginMarkPx  float64 `json:"marginMarkPx"`
	SwapMarkPx    float64 `json:"swapMarkPx"`
	PercentDiff   float64 `json:"percentDiff"`
	ActualDiff    float64 `json:"actualDiff"`
	IsContango    bool    `json:"isContango"`
	TermStructure string  `json:"termStructure"`
}

type FundingInfo struct {
	InstID          string  // Instrument ID (e.g., BTC-USDT-SWAP)
	FundingRate     float64 // Current or next funding rate
	NextFundingTime int64   // Unix ms timestamp for next funding event
}

type FeeInfo struct {
	SpotTaker    float64 // e.g., 0.001
	SwapTaker    float64 // e.g., 0.0005
	MarginBorrow float64 // hourly, e.g., 0.0002
}

type HTTPClient struct {
	client *http.Client
	config Config
}

type InterestRate struct {
	Ccy          string  `json:"ccy"`
	InterestRate float64 `json:"interestRate,string"`
}

type OKXInterestRateResponse struct {
	Code string         `json:"code"`
	Msg  string         `json:"msg"`
	Data []InterestRate `json:"data"`
}

// Order book structures
type OrderBookLevel struct {
	Price  float64 `json:"price"`
	Size   float64 `json:"size"`
	Orders int     `json:"orders"`
}

type OrderBook struct {
	InstID string           `json:"instId"`
	Bids   []OrderBookLevel `json:"bids"`
	Asks   []OrderBookLevel `json:"asks"`
	TS     string           `json:"ts"`
}

type OKXOrderBookResponse struct {
	Code string      `json:"code"`
	Msg  string      `json:"msg"`
	Data []OrderBook `json:"data"`
}

// Weighted pricing results
type WeightedPriceResult struct {
	Symbol             string  `json:"symbol"`
	Side               string  `json:"side"` // "buy" or "sell"
	TradeSize          float64 `json:"tradeSize"`
	WeightedPrice      float64 `json:"weightedPrice"`
	TotalCost          float64 `json:"totalCost"`
	Liquidity          float64 `json:"liquidity"`
	HasEnoughLiquidity bool    `json:"hasEnoughLiquidity"`
	Slippage           float64 `json:"slippage"` // in percentage
}

// Enhanced arbitrage result with real execution prices
type RealArbitrageResult struct {
	BaseSymbol         string  `json:"baseSymbol"`
	MarginBuyPrice     float64 `json:"marginBuyPrice"`  // Weighted price to buy on margin
	MarginSellPrice    float64 `json:"marginSellPrice"` // Weighted price to sell on margin
	SwapBuyPrice       float64 `json:"swapBuyPrice"`    // Weighted price to buy on swap
	SwapSellPrice      float64 `json:"swapSellPrice"`   // Weighted price to sell on swap
	PercentDiff        float64 `json:"percentDiff"`
	ActualDiff         float64 `json:"actualDiff"`
	IsContango         bool    `json:"isContango"`
	TermStructure      string  `json:"termStructure"`
	MarginLiquidity    float64 `json:"marginLiquidity"`
	SwapLiquidity      float64 `json:"swapLiquidity"`
	HasEnoughLiquidity bool    `json:"hasEnoughLiquidity"`
	MarginSlippage     float64 `json:"marginSlippage"`
	SwapSlippage       float64 `json:"swapSlippage"`
}

// Trading configuration
type TradingConfig struct {
	TradeSizeUSD    float64 `json:"tradeSizeUSD"`    // Size of each trade in USD
	MinLiquidityUSD float64 `json:"minLiquidityUSD"` // Minimum liquidity required
	MaxSlippage     float64 `json:"maxSlippage"`     // Maximum acceptable slippage in %
	OrderBookDepth  int     `json:"orderBookDepth"`  // Number of order book levels to fetch
}
