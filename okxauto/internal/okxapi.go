package gookx

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"
)

// ... existing code ...

func NewHTTPClient(config Config) *HTTPClient {
	if config.APIKey == "" {
		config.APIKey = os.Getenv("OKX_API_KEY")
	}
	if config.APISecret == "" {
		config.APISecret = os.Getenv("OKX_API_SECRET")
	}
	if config.APIPassphrase == "" {
		config.APIPassphrase = os.Getenv("OKX_API_PASSPHRASE")
	}
	return &HTTPClient{
		client: &http.Client{
			Timeout: config.HTTPTimeout,
		},
		config: config,
	}
}

func (h *HTTPClient) MakeRequest(ctx context.Context, url string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("User-Agent", h.config.UserAgent)
	req.Header.Set("Accept", "application/json")

	resp, err := h.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	return body, nil
}

func (h *HTTPClient) FetchMarkPrices(ctx context.Context, instType string) (map[string]MarkPrice, error) {
	url := fmt.Sprintf("https://www.okx.com/api/v5/public/mark-price?instType=%s", instType)
	body, err := h.MakeRequest(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("mark price request failed: %w", err)
	}

	var response OKXMarkPriceResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal mark price response: %w", err)
	}

	if response.Code != "0" {
		return nil, fmt.Errorf("API error: %s - %s", response.Code, response.Msg)
	}

	markPriceMap := make(map[string]MarkPrice)
	for _, item := range response.Data {
		if item.InstID != "" {
			markPriceMap[item.InstID] = item
		}
	}

	return markPriceMap, nil
}

func (h *HTTPClient) FetchInstruments(ctx context.Context, instType, quoteCcy string) ([]Instrument, error) {
	url := fmt.Sprintf("https://www.okx.com/api/v5/public/instruments?instType=%s", instType)
	body, err := h.MakeRequest(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("instruments request failed: %w", err)
	}

	var response OKXInstrumentResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal instruments response: %w", err)
	}

	if response.Code != "0" {
		return nil, fmt.Errorf("API error: %s - %s", response.Code, response.Msg)
	}

	var filteredInstruments []Instrument
	for _, inst := range response.Data {
		if inst.State != "live" {
			continue
		}
		if quoteCcy != "" && inst.QuoteCcy != quoteCcy {
			continue
		}
		filteredInstruments = append(filteredInstruments, inst)
	}

	return filteredInstruments, nil
}

type okxFundingResponse struct {
	Code string `json:"code"`
	Msg  string `json:"msg"`
	Data []struct {
		InstID          string `json:"instId"`
		FundingRate     string `json:"fundingRate"`
		NextFundingTime string `json:"nextFundingTime"`
	} `json:"data"`
}

func (h *HTTPClient) FetchFundingInfo(ctx context.Context, instID string) (FundingInfo, error) {
	url := fmt.Sprintf("https://www.okx.com/api/v5/public/funding-rate?instId=%s", instID)
	body, err := h.MakeRequest(ctx, url)
	if err != nil {
		return FundingInfo{}, fmt.Errorf("funding rate request failed: %w", err)
	}

	var resp okxFundingResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return FundingInfo{}, fmt.Errorf("failed to unmarshal funding response: %w", err)
	}
	if resp.Code != "0" || len(resp.Data) == 0 {
		return FundingInfo{}, fmt.Errorf("API error: %s - %s", resp.Code, resp.Msg)
	}
	data := resp.Data[0]
	fundingRate, err := strconv.ParseFloat(data.FundingRate, 64)
	if err != nil {
		return FundingInfo{}, fmt.Errorf("failed to parse fundingRate: %w", err)
	}
	nextFundingTime, err := strconv.ParseInt(data.NextFundingTime, 10, 64)
	if err != nil {
		return FundingInfo{}, fmt.Errorf("failed to parse nextFundingTime: %w", err)
	}
	return FundingInfo{
		InstID:          data.InstID,
		FundingRate:     fundingRate,
		NextFundingTime: nextFundingTime,
	}, nil
}

// Fee fetching (public endpoints, fallback to constants if needed)
type okxFeeResponse struct {
	Code string `json:"code"`
	Msg  string `json:"msg"`
	Data []struct {
		Taker string `json:"taker"`
	} `json:"data"`
}

func (h *HTTPClient) FetchFeeInfo(ctx context.Context) (FeeInfo, error) {
	var fee FeeInfo
	// Spot taker fee
	spotURL := "https://www.okx.com/api/v5/account/trade-fee?instType=SPOT"
	spotBody, err := h.MakeRequest(ctx, spotURL)
	if err == nil {
		var resp okxFeeResponse
		if err := json.Unmarshal(spotBody, &resp); err == nil && resp.Code == "0" && len(resp.Data) > 0 {
			fee.SpotTaker, _ = strconv.ParseFloat(resp.Data[0].Taker, 64)
		}
	}
	if fee.SpotTaker == 0 {
		fee.SpotTaker = 0.001 // fallback default
	}
	// Swap taker fee
	swapURL := "https://www.okx.com/api/v5/account/trade-fee?instType=SWAP"
	swapBody, err := h.MakeRequest(ctx, swapURL)
	if err == nil {
		var resp okxFeeResponse
		if err := json.Unmarshal(swapBody, &resp); err == nil && resp.Code == "0" && len(resp.Data) > 0 {
			fee.SwapTaker, _ = strconv.ParseFloat(resp.Data[0].Taker, 64)
		}
	}
	if fee.SwapTaker == 0 {
		fee.SwapTaker = 0.0005 // fallback default
	}
	// Margin borrow fee (no public endpoint, use constant)
	fee.MarginBorrow = 0.0002 // 0.02% per hour
	return fee, nil
}

// Helper for OKX signature
func signOKX(ts, method, path, body, secret string) string {
	prehash := ts + method + path + body
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(prehash))
	return base64.StdEncoding.EncodeToString(h.Sum(nil))
}

// Private signed GET request
func (h *HTTPClient) MakeSignedRequest(ctx context.Context, method, path, query string) ([]byte, error) {
	url := "https://www.okx.com" + path
	if query != "" {
		url += "?" + query
	}
	// Use ISO8601 timestamp as required by OKX
	ts := time.Now().UTC().Format("2006-01-02T15:04:05.000Z")
	body := ""
	signature := signOKX(ts, method, path, body, h.config.APISecret)

	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create signed request: %w", err)
	}
	req.Header.Set("OK-ACCESS-KEY", h.config.APIKey)
	req.Header.Set("OK-ACCESS-SIGN", signature)
	req.Header.Set("OK-ACCESS-TIMESTAMP", ts)
	req.Header.Set("OK-ACCESS-PASSPHRASE", h.config.APIPassphrase)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", h.config.UserAgent)

	resp, err := h.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("signed request failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}
	return bodyBytes, nil
}

// Fetch interest rates (private)
func (h *HTTPClient) FetchInterestRates(ctx context.Context) (map[string]float64, error) {
	path := "/api/v5/account/interest-rate"
	body, err := h.MakeSignedRequest(ctx, "GET", path, "")
	if err != nil {
		return nil, fmt.Errorf("interest rate request failed: %w", err)
	}
	var resp OKXInterestRateResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("failed to unmarshal interest rate response: %w", err)
	}
	if resp.Code != "0" {
		return nil, fmt.Errorf("API error: %s - %s", resp.Code, resp.Msg)
	}
	rates := make(map[string]float64)
	for _, ir := range resp.Data {
		rates[ir.Ccy] = ir.InterestRate
	}
	return rates, nil
}

// Fetch order book for a specific instrument
func (h *HTTPClient) FetchOrderBook(ctx context.Context, instID string, depth int) (*OrderBook, error) {
	url := fmt.Sprintf("https://www.okx.com/api/v5/market/books?instId=%s&sz=%d", instID, depth)
	body, err := h.MakeRequest(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("order book request failed: %w", err)
	}

	// OKX returns order book as raw JSON arrays, so we need to parse it manually
	var rawResponse struct {
		Code string `json:"code"`
		Msg  string `json:"msg"`
		Data []struct {
			InstID string     `json:"instId"`
			Bids   [][]string `json:"bids"`
			Asks   [][]string `json:"asks"`
			TS     string     `json:"ts"`
		} `json:"data"`
	}

	if err := json.Unmarshal(body, &rawResponse); err != nil {
		return nil, fmt.Errorf("failed to unmarshal order book response: %w", err)
	}

	if rawResponse.Code != "0" {
		return nil, fmt.Errorf("API error: %s - %s", rawResponse.Code, rawResponse.Msg)
	}

	if len(rawResponse.Data) == 0 {
		return nil, fmt.Errorf("no order book data received")
	}

	rawData := rawResponse.Data[0]

	// Parse bids and asks
	bids, err := parseOrderBookLevels(rawData.Bids)
	if err != nil {
		return nil, fmt.Errorf("failed to parse bids: %w", err)
	}

	asks, err := parseOrderBookLevels(rawData.Asks)
	if err != nil {
		return nil, fmt.Errorf("failed to parse asks: %w", err)
	}

	return &OrderBook{
		InstID: rawData.InstID,
		Bids:   bids,
		Asks:   asks,
		TS:     rawData.TS,
	}, nil
}

// Parse order book levels from OKX format
func parseOrderBookLevels(rawData [][]string) ([]OrderBookLevel, error) {
	var levels []OrderBookLevel
	for _, level := range rawData {
		if len(level) < 2 {
			continue
		}

		price, err := strconv.ParseFloat(level[0], 64)
		if err != nil {
			continue
		}

		size, err := strconv.ParseFloat(level[1], 64)
		if err != nil {
			continue
		}

		orders := 1
		if len(level) >= 3 {
			if ordersInt, err := strconv.Atoi(level[2]); err == nil {
				orders = ordersInt
			}
		}

		levels = append(levels, OrderBookLevel{
			Price:  price,
			Size:   size,
			Orders: orders,
		})
	}
	return levels, nil
}

// Calculate weighted average price for a given trade size
func CalculateWeightedPrice(orderBook *OrderBook, side string, tradeSize float64) (*WeightedPriceResult, error) {
	var levels []OrderBookLevel
	var bestPrice float64

	if side == "buy" {
		levels = orderBook.Asks // Buy from asks (sell orders)
		if len(levels) == 0 {
			return nil, fmt.Errorf("no ask orders available")
		}
		bestPrice = levels[0].Price
	} else if side == "sell" {
		levels = orderBook.Bids // Sell to bids (buy orders)
		if len(levels) == 0 {
			return nil, fmt.Errorf("no bid orders available")
		}
		bestPrice = levels[0].Price
	} else {
		return nil, fmt.Errorf("invalid side: %s", side)
	}

	var totalCost float64
	var remainingSize = tradeSize
	var weightedPrice float64
	var liquidity float64

	for _, level := range levels {
		if remainingSize <= 0 {
			break
		}

		levelSize := level.Size
		if remainingSize < levelSize {
			levelSize = remainingSize
		}

		cost := levelSize * level.Price
		totalCost += cost
		remainingSize -= levelSize
		liquidity += levelSize * level.Price
	}

	if remainingSize > 0 {
		// Not enough liquidity
		return &WeightedPriceResult{
			Symbol:             orderBook.InstID,
			Side:               side,
			TradeSize:          tradeSize,
			WeightedPrice:      0,
			TotalCost:          0,
			Liquidity:          liquidity,
			HasEnoughLiquidity: false,
			Slippage:           0,
		}, nil
	}

	weightedPrice = totalCost / tradeSize

	// Calculate slippage as percentage difference from best price
	slippage := 0.0
	if side == "buy" {
		slippage = ((weightedPrice - bestPrice) / bestPrice) * 100
	} else {
		slippage = ((bestPrice - weightedPrice) / bestPrice) * 100
	}

	return &WeightedPriceResult{
		Symbol:             orderBook.InstID,
		Side:               side,
		TradeSize:          tradeSize,
		WeightedPrice:      weightedPrice,
		TotalCost:          totalCost,
		Liquidity:          liquidity,
		HasEnoughLiquidity: true,
		Slippage:           slippage,
	}, nil
}
