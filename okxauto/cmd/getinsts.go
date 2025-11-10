package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"time"

	gookx "okxauto/internal"
	// _ "github.com/joho/godotenv/autoload"
)

func main() {
	// Parse command line flags
	var (
		marginInstType = flag.String("margin-type", "MARGIN", "Margin instrument type")
		swapInstType   = flag.String("swap-type", "SWAP", "Swap instrument type")
		quoteCurrency  = flag.String("quote", "USDT", "Quote currency")
		timeout        = flag.Duration("timeout", 30*time.Second, "HTTP timeout")
		topN           = flag.Int("top", 10, "Number of top results to show")
		minDiff        = flag.Float64("min-diff", 0.24, "Minimum percentage difference to include")

		// New flags for order book analysis
		useOrderBook    = flag.Bool("orderbook", false, "Use order book data instead of mark prices")
		tradeSizeUSD    = flag.Float64("trade-size", 1000.0, "Trade size in USD for order book analysis")
		minLiquidityUSD = flag.Float64("min-liquidity", 10000.0, "Minimum liquidity required in USD")
		maxSlippage     = flag.Float64("max-slippage", 0.5, "Maximum acceptable slippage in percentage")
		orderBookDepth  = flag.Int("depth", 20, "Order book depth to fetch")
	)
	flag.Parse()

	// Create configuration
	config := gookx.Config{
		MarginInstType: *marginInstType,
		SwapInstType:   *swapInstType,
		QuoteCurrency:  *quoteCurrency,
		HTTPTimeout:    *timeout,
		UserAgent:      "OKX-Instrument-Analyzer/1.0",
	}

	// Create trading configuration for order book analysis
	tradingConfig := gookx.TradingConfig{
		TradeSizeUSD:    *tradeSizeUSD,
		MinLiquidityUSD: *minLiquidityUSD,
		MaxSlippage:     *maxSlippage,
		OrderBookDepth:  *orderBookDepth,
	}

	// Create HTTP client
	client := gookx.NewHTTPClient(config)
	ctx := context.Background()

	if *useOrderBook {
		// Use order book analysis
		fmt.Println("Using order book analysis for real execution prices...")
		fmt.Printf("Trade size: $%.2f, Min liquidity: $%.2f, Max slippage: %.2f%%, Order book depth: %d\n",
			tradingConfig.TradeSizeUSD, tradingConfig.MinLiquidityUSD, tradingConfig.MaxSlippage, tradingConfig.OrderBookDepth)

		// Fetch instruments first
		fmt.Println("Fetching instruments...")
		marginInstruments, err := client.FetchInstruments(ctx, config.MarginInstType, config.QuoteCurrency)
		if err != nil {
			log.Fatalf("Failed to fetch margin instruments: %v", err)
		}
		fmt.Printf("Fetched %d margin instruments\n", len(marginInstruments))

		swapInstruments, err := client.FetchInstruments(ctx, config.SwapInstType, "")
		if err != nil {
			log.Fatalf("Failed to fetch swap instruments: %v", err)
		}
		fmt.Printf("Fetched %d swap instruments\n", len(swapInstruments))

		// Find matching symbols
		matchingSymbols := gookx.FindMatchingSymbols(marginInstruments, swapInstruments)
		fmt.Printf("Found %d matching symbols between %s and %s instruments\n",
			len(matchingSymbols), config.MarginInstType, config.SwapInstType)

		// Calculate real arbitrage opportunities using order books
		realResults, err := gookx.CalculateRealArbitrageOpportunities(matchingSymbols, client, tradingConfig, ctx)
		if err != nil {
			log.Fatalf("Failed to calculate real arbitrage opportunities: %v", err)
		}

		// Filter by minimum difference
		var filteredResults []gookx.RealArbitrageResult
		for _, result := range realResults {
			if result.PercentDiff >= *minDiff {
				filteredResults = append(filteredResults, result)
			}
		}

		// Limit to top N results
		if len(filteredResults) > *topN {
			filteredResults = filteredResults[:*topN]
		}

		// Fetch fee info
		fees, err := client.FetchFeeInfo(ctx)
		if err != nil {
			log.Fatalf("Failed to fetch fee info: %v", err)
		}

		// Fetch borrow rates
		borrowRates, err := client.FetchInterestRates(ctx)
		if err != nil {
			log.Printf("Warning: could not fetch borrow rates, will use default: %v", err)
			borrowRates = map[string]float64{}
		}

		// Calculate fees for each result
		feesMap := make(map[string]float64)
		for _, result := range filteredResults {
			// Create a DiffResult for fee calculation
			diffResult := gookx.DiffResult{
				BaseSymbol:    result.BaseSymbol,
				TermStructure: result.TermStructure,
			}
			feesMap[result.BaseSymbol] = gookx.EstimateFees(diffResult, fees, borrowRates)
		}

		// Fetch funding info for the results
		fundingMap := make(map[string]struct {
			Rate          float64
			TimeToFunding time.Duration
		})
		for _, result := range filteredResults {
			// Find the swap instrument ID
			var swapInstID string
			for _, match := range matchingSymbols {
				if match.BaseSymbol == result.BaseSymbol {
					swapInstID = match.Swap.InstID
					break
				}
			}
			if swapInstID == "" {
				continue
			}

			funding, err := client.FetchFundingInfo(ctx, swapInstID)
			if err != nil {
				fundingMap[result.BaseSymbol] = struct {
					Rate          float64
					TimeToFunding time.Duration
				}{0, 0}
			} else {
				tf := time.Until(time.UnixMilli(funding.NextFundingTime))
				fundingMap[result.BaseSymbol] = struct {
					Rate          float64
					TimeToFunding time.Duration
				}{funding.FundingRate, tf}
			}
		}

		// Print results
		gookx.PrintRealArbitrageResults(filteredResults, fundingMap, feesMap, *minDiff)

	} else {
		// Use original mark price analysis
		fmt.Println("Using mark price analysis...")

		// Fetch mark prices
		fmt.Println("Fetching mark prices...")
		marginMarkPrices, err := client.FetchMarkPrices(ctx, config.MarginInstType)
		if err != nil {
			log.Fatalf("Failed to fetch margin mark prices: %v", err)
		}
		fmt.Printf("Fetched mark prices for %d margin instruments\n", len(marginMarkPrices))

		swapMarkPrices, err := client.FetchMarkPrices(ctx, config.SwapInstType)
		if err != nil {
			log.Fatalf("Failed to fetch swap mark prices: %v", err)
		}
		fmt.Printf("Fetched mark prices for %d swap instruments\n", len(swapMarkPrices))

		// Fetch instruments
		fmt.Println("Fetching instruments...")
		marginInstruments, err := client.FetchInstruments(ctx, config.MarginInstType, config.QuoteCurrency)
		if err != nil {
			log.Fatalf("Failed to fetch margin instruments: %v", err)
		}
		fmt.Printf("Fetched %d margin instruments\n", len(marginInstruments))

		swapInstruments, err := client.FetchInstruments(ctx, config.SwapInstType, "")
		if err != nil {
			log.Fatalf("Failed to fetch swap instruments: %v", err)
		}
		fmt.Printf("Fetched %d swap instruments\n", len(swapInstruments))

		// Fuse mark price data with instruments
		fusedMargin := gookx.FuseData(marginInstruments, marginMarkPrices)
		fusedSwap := gookx.FuseData(swapInstruments, swapMarkPrices)

		// Find matching symbols
		matchingSymbols := gookx.FindMatchingSymbols(fusedMargin, fusedSwap)
		fmt.Printf("Found %d matching symbols between %s and %s instruments\n",
			len(matchingSymbols), config.MarginInstType, config.SwapInstType)

		// Calculate and print top mark price differences
		diffs, err := gookx.CalculateTopMarkPxDiffs(matchingSymbols, *topN, *minDiff)
		if err != nil {
			log.Fatalf("Failed to calculate mark price differences: %v", err)
		}

		// Fetch fee info once
		fees, err := client.FetchFeeInfo(ctx)
		if err != nil {
			log.Fatalf("Failed to fetch fee info: %v", err)
		}

		// Fetch borrow rates once (private endpoint)
		borrowRates, err := client.FetchInterestRates(ctx)
		if err != nil {
			log.Printf("Warning: could not fetch borrow rates, will use default: %v", err)
			borrowRates = map[string]float64{}
		}

		// Fetch funding info for only the top-N symbols and build a map
		fundingMap := make(map[string]struct {
			Rate          float64
			TimeToFunding time.Duration
		})
		feesMap := make(map[string]float64)
		for _, d := range diffs {
			var swapInstID string
			for _, match := range matchingSymbols {
				if match.BaseSymbol == d.BaseSymbol {
					swapInstID = match.Swap.InstID
					break
				}
			}
			if swapInstID == "" {
				continue
			}
			funding, err := client.FetchFundingInfo(ctx, swapInstID)
			if err != nil {
				fundingMap[d.BaseSymbol] = struct {
					Rate          float64
					TimeToFunding time.Duration
				}{0, 0}
			} else {
				tf := time.Until(time.UnixMilli(funding.NextFundingTime))
				fundingMap[d.BaseSymbol] = struct {
					Rate          float64
					TimeToFunding time.Duration
				}{funding.FundingRate, tf}
			}
			feesMap[d.BaseSymbol] = gookx.EstimateFees(d, fees, borrowRates)
		}

		gookx.PrintTopMarkPxDiffsWithFundingAndFees(diffs, fundingMap, feesMap, *minDiff)
	}
}
