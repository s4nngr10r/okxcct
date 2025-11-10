package gookx

import (
	"context"
	"fmt"
	"log"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"
)

func FuseData(instruments []Instrument, markPrices map[string]MarkPrice) []Instrument {
	var fused []Instrument
	for _, inst := range instruments {
		fusedInst := inst
		if markPrice, exists := markPrices[inst.InstID]; exists {
			if markPrice.MarkPx != "" {
				fusedInst.MarkPx = markPrice.MarkPx
			}
		}
		fused = append(fused, fusedInst)
	}
	return fused
}

func ExtractBaseSymbol(instID string) string {
	parts := strings.Split(instID, "-")
	if len(parts) >= 2 {
		return parts[0]
	}
	return instID
}

func FindMatchingSymbols(marginInstruments, swapInstruments []Instrument) []MatchingSymbol {
	marginSymbols := make(map[string]Instrument)
	swapSymbols := make(map[string]Instrument)
	for _, inst := range marginInstruments {
		baseSymbol := ExtractBaseSymbol(inst.InstID)
		marginSymbols[baseSymbol] = inst
	}
	for _, inst := range swapInstruments {
		baseSymbol := ExtractBaseSymbol(inst.InstID)
		swapSymbols[baseSymbol] = inst
	}
	var matching []MatchingSymbol
	for baseSymbol, marginInst := range marginSymbols {
		if swapInst, exists := swapSymbols[baseSymbol]; exists {
			matching = append(matching, MatchingSymbol{
				BaseSymbol: baseSymbol,
				Margin:     marginInst,
				Swap:       swapInst,
			})
		}
	}
	return matching
}

func ParseFloat(s string) (float64, error) {
	if s == "" {
		return 0, fmt.Errorf("empty string")
	}
	return strconv.ParseFloat(s, 64)
}

func CalculateTopMarkPxDiffs(matches []MatchingSymbol, topN int, minDiff float64) ([]DiffResult, error) {
	var diffs []DiffResult

	for _, match := range matches {
		marginPx, err := ParseFloat(match.Margin.MarkPx)
		if err != nil {
			log.Printf("Warning: failed to parse margin markPx for %s: %v", match.BaseSymbol, err)
			continue
		}
		swapPx, err := ParseFloat(match.Swap.MarkPx)
		if err != nil {
			log.Printf("Warning: failed to parse swap markPx for %s: %v", match.BaseSymbol, err)
			continue
		}
		if marginPx <= 0 || swapPx <= 0 {
			continue
		}
		actualDiff := swapPx - marginPx
		meanPx := (marginPx + swapPx) / 2
		percentDiff := 100 * math.Abs(actualDiff) / meanPx

		if percentDiff < minDiff {
			continue
		}
		isContango := actualDiff > 0
		termStructure := "Backwardation"
		if isContango {
			termStructure = "Contango"
		}
		diffs = append(diffs, DiffResult{
			BaseSymbol:    match.BaseSymbol,
			MarginMarkPx:  marginPx,
			SwapMarkPx:    swapPx,
			PercentDiff:   percentDiff,
			ActualDiff:    actualDiff,
			IsContango:    isContango,
			TermStructure: termStructure,
		})
	}

	sort.Slice(diffs, func(i, j int) bool {
		return diffs[i].PercentDiff > diffs[j].PercentDiff
	})
	if len(diffs) > topN {
		diffs = diffs[:topN]
	}
	return diffs, nil
}

func PrintTopMarkPxDiffsWithFunding(diffs []DiffResult, fundingMap map[string]struct {
	Rate          float64
	TimeToFunding time.Duration
}, minDiff float64) {
	if minDiff > 0 {
		fmt.Printf("\nTop %d symbols with %% markPx difference >= %.2f%% (swap vs margin):\n", len(diffs), minDiff)
	} else {
		fmt.Printf("\nTop %d symbols by %% markPx difference (swap vs margin):\n", len(diffs))
	}
	fmt.Printf("%-12s %-15s %-15s %-18s %-10s %-15s %-12s %-16s\n", "Symbol", "Margin", "Swap", "Actual Diff", "% Diff", "Structure", "FundingRate", "TimeToFunding")
	fmt.Println(strings.Repeat("-", 125))
	for _, d := range diffs {
		funding := fundingMap[d.BaseSymbol]
		diffSign := "+"
		if d.ActualDiff < 0 {
			diffSign = ""
		}
		actualDiffStr := fmt.Sprintf("%s%.6f", diffSign, d.ActualDiff)
		fmt.Printf("%-12s %-15.6f %-15.6f %-18s %-10.2f %-15s %-12.6f %-16s\n",
			d.BaseSymbol, d.MarginMarkPx, d.SwapMarkPx, actualDiffStr, d.PercentDiff, d.TermStructure, funding.Rate, funding.TimeToFunding.Round(time.Second))
	}
}

func PrintTopMarkPxDiffsWithFundingAndFees(diffs []DiffResult, fundingMap map[string]struct {
	Rate          float64
	TimeToFunding time.Duration
}, feesMap map[string]float64, minDiff float64) {
	if minDiff > 0 {
		fmt.Printf("\nTop %d symbols with %% markPx difference >= %.2f%% (swap vs margin):\n", len(diffs), minDiff)
	} else {
		fmt.Printf("\nTop %d symbols by %% markPx difference (swap vs margin):\n", len(diffs))
	}
	fmt.Printf("%-12s %-15s %-15s %-18s %-10s %-15s %-12s %-16s %-10s %-12s\n", "Symbol", "Margin", "Swap", "Actual Diff", "% Diff", "Structure", "FundingRate", "TimeToFunding", "Fees", "ActualProfit")
	fmt.Println(strings.Repeat("-", 152))
	for _, d := range diffs {
		funding := fundingMap[d.BaseSymbol]
		fees := feesMap[d.BaseSymbol]
		diffSign := "+"
		if d.ActualDiff < 0 {
			diffSign = ""
		}
		actualDiffStr := fmt.Sprintf("%s%.6f", diffSign, d.ActualDiff)
		feesPct := fees * 100
		actualProfit := d.PercentDiff - feesPct
		if actualProfit < 0.06 {
			continue // skip if less than 0.1%%
		}
		fmt.Printf("%-12s %-15.6f %-15.6f %-18s %-10.2f %-15s %-12.6f %-16s %-9.4f%%   %-10.2f%%\n",
			d.BaseSymbol, d.MarginMarkPx, d.SwapMarkPx, actualDiffStr, d.PercentDiff, d.TermStructure, funding.Rate, funding.TimeToFunding.Round(time.Second), feesPct, actualProfit)
	}
}

func EstimateFees(diff DiffResult, fees FeeInfo, borrowRates map[string]float64) float64 {
	// Notional is 1 for simplicity
	fee := (fees.SpotTaker * 2) + (fees.SwapTaker * 2)
	if diff.TermStructure == "Backwardation" {
		borrow := fees.MarginBorrow
		if r, ok := borrowRates[diff.BaseSymbol]; ok && r > 0 {
			borrow = r
		}
		fee += borrow * 1 // 1 hour
	}
	return fee
}

// Calculate real arbitrage opportunities using order book data
func CalculateRealArbitrageOpportunities(matches []MatchingSymbol, client *HTTPClient, config TradingConfig, ctx context.Context) ([]RealArbitrageResult, error) {
	var results []RealArbitrageResult

	for _, match := range matches {
		// Fetch order books for both instruments
		marginOrderBook, err := client.FetchOrderBook(ctx, match.Margin.InstID, config.OrderBookDepth)
		if err != nil {
			fmt.Printf("Warning: failed to fetch margin order book for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		swapOrderBook, err := client.FetchOrderBook(ctx, match.Swap.InstID, config.OrderBookDepth)
		if err != nil {
			fmt.Printf("Warning: failed to fetch swap order book for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		// Calculate trade size in base currency (approximate)
		// We'll use the margin price as reference for calculating quantity
		marginPrice, err := ParseFloat(match.Margin.MarkPx)
		if err != nil || marginPrice <= 0 {
			continue
		}

		tradeSizeBase := config.TradeSizeUSD / marginPrice

		// Calculate weighted prices for all sides
		marginBuy, err := CalculateWeightedPrice(marginOrderBook, "buy", tradeSizeBase)
		if err != nil {
			fmt.Printf("Warning: failed to calculate margin buy price for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		marginSell, err := CalculateWeightedPrice(marginOrderBook, "sell", tradeSizeBase)
		if err != nil {
			fmt.Printf("Warning: failed to calculate margin sell price for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		swapBuy, err := CalculateWeightedPrice(swapOrderBook, "buy", tradeSizeBase)
		if err != nil {
			fmt.Printf("Warning: failed to calculate swap buy price for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		swapSell, err := CalculateWeightedPrice(swapOrderBook, "sell", tradeSizeBase)
		if err != nil {
			fmt.Printf("Warning: failed to calculate swap sell price for %s: %v\n", match.BaseSymbol, err)
			continue
		}

		// Check liquidity requirements
		hasEnoughLiquidity := marginBuy.HasEnoughLiquidity && marginSell.HasEnoughLiquidity &&
			swapBuy.HasEnoughLiquidity && swapSell.HasEnoughLiquidity

		if !hasEnoughLiquidity {
			continue
		}

		// Check slippage limits
		if marginBuy.Slippage > config.MaxSlippage || marginSell.Slippage > config.MaxSlippage ||
			swapBuy.Slippage > config.MaxSlippage || swapSell.Slippage > config.MaxSlippage {
			continue
		}

		// Calculate arbitrage opportunities
		// Contango: Buy margin, sell swap
		contangoDiff := swapSell.WeightedPrice - marginBuy.WeightedPrice
		contangoPercent := (contangoDiff / ((swapSell.WeightedPrice + marginBuy.WeightedPrice) / 2)) * 100

		// Backwardation: Sell margin, buy swap
		backwardationDiff := marginSell.WeightedPrice - swapBuy.WeightedPrice
		backwardationPercent := (backwardationDiff / ((marginSell.WeightedPrice + swapBuy.WeightedPrice) / 2)) * 100

		// Determine which direction is more profitable
		var result RealArbitrageResult
		if contangoPercent > backwardationPercent && contangoPercent > 0 {
			result = RealArbitrageResult{
				BaseSymbol:         match.BaseSymbol,
				MarginBuyPrice:     marginBuy.WeightedPrice,
				MarginSellPrice:    marginSell.WeightedPrice,
				SwapBuyPrice:       swapBuy.WeightedPrice,
				SwapSellPrice:      swapSell.WeightedPrice,
				PercentDiff:        contangoPercent,
				ActualDiff:         contangoDiff,
				IsContango:         true,
				TermStructure:      "Contango",
				MarginLiquidity:    marginBuy.Liquidity,
				SwapLiquidity:      swapSell.Liquidity,
				HasEnoughLiquidity: hasEnoughLiquidity,
				MarginSlippage:     marginBuy.Slippage,
				SwapSlippage:       swapSell.Slippage,
			}
		} else if backwardationPercent > 0 {
			result = RealArbitrageResult{
				BaseSymbol:         match.BaseSymbol,
				MarginBuyPrice:     marginBuy.WeightedPrice,
				MarginSellPrice:    marginSell.WeightedPrice,
				SwapBuyPrice:       swapBuy.WeightedPrice,
				SwapSellPrice:      swapSell.WeightedPrice,
				PercentDiff:        backwardationPercent,
				ActualDiff:         backwardationDiff,
				IsContango:         false,
				TermStructure:      "Backwardation",
				MarginLiquidity:    marginSell.Liquidity,
				SwapLiquidity:      swapBuy.Liquidity,
				HasEnoughLiquidity: hasEnoughLiquidity,
				MarginSlippage:     marginSell.Slippage,
				SwapSlippage:       swapBuy.Slippage,
			}
		} else {
			continue // No profitable opportunity
		}

		results = append(results, result)
	}

	// Sort by percentage difference
	sort.Slice(results, func(i, j int) bool {
		return results[i].PercentDiff > results[j].PercentDiff
	})

	return results, nil
}

// Print real arbitrage results with order book data
func PrintRealArbitrageResults(results []RealArbitrageResult, fundingMap map[string]struct {
	Rate          float64
	TimeToFunding time.Duration
}, feesMap map[string]float64, minDiff float64) {
	if minDiff > 0 {
		fmt.Printf("\nTop %d symbols with real execution prices (%% difference >= %.2f%%):\n", len(results), minDiff)
	} else {
		fmt.Printf("\nTop %d symbols with real execution prices:\n", len(results))
	}

	fmt.Printf("%-12s %-15s %-15s %-15s %-15s %-10s %-15s %-12s %-16s %-10s %-12s %-12s\n",
		"Symbol", "MarginBuy", "MarginSell", "SwapBuy", "SwapSell", "% Diff", "Structure", "FundingRate", "TimeToFunding", "Fees", "ActualProfit", "Slippage")
	fmt.Println(strings.Repeat("-", 180))

	for _, r := range results {
		funding := fundingMap[r.BaseSymbol]
		fees := feesMap[r.BaseSymbol]

		feesPct := fees * 100
		actualProfit := r.PercentDiff - feesPct

		// Calculate average slippage
		avgSlippage := (r.MarginSlippage + r.SwapSlippage) / 2

		if actualProfit < 0.06 {
			continue // skip if less than 0.06% profit
		}

		fmt.Printf("%-12s %-15.6f %-15.6f %-15.6f %-15.6f %-10.2f %-15s %-12.6f %-16s %-9.4f%%   %-10.2f%%   %-10.4f%%\n",
			r.BaseSymbol, r.MarginBuyPrice, r.MarginSellPrice, r.SwapBuyPrice, r.SwapSellPrice,
			r.PercentDiff, r.TermStructure, funding.Rate, funding.TimeToFunding.Round(time.Second),
			feesPct, actualProfit, avgSlippage)
	}
}
