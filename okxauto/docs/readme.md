# okxauto

A modular Go system for analyzing and comparing OKX margin and swap instruments, designed for automated spread/funding/fair value monitoring and research.

## Features
- Fetches live instrument and mark price data from OKX
- Matches symbols between margin and swap markets
- Calculates and displays top mark price differences
- Outputs results to JSON for further analysis
- Modular, idiomatic Go codebase (internal package, cmd entrypoint)

## Architecture

- **cmd/getinsts.go**: Main entrypoint, CLI, orchestration
- **internal/models.go**: Data structures (Instrument, MarkPrice, etc.)
- **internal/okxapi.go**: OKX API logic (fetching instruments, mark prices)
- **internal/analyzer.go**: Business logic (matching, diff calculation)
- **internal/storage.go**: File I/O (saving results)

## Data Structures

### Config
```go
type Config struct {
    MarginInstType string
    SwapInstType   string
    QuoteCurrency  string
    HTTPTimeout    time.Duration
    UserAgent      string
}
```
Configuration for the HTTP client and API queries.

### Instrument
```go
type Instrument struct {
    InstID     string
    InstType   string
    BaseCcy    string
    QuoteCcy   string
    State      string
    MarkPx     string
    Lever      string
    LotSz      string
    TickSz     string
    MinSz      string
    MaxSz      string
    Extra      map[string]interface{}
}
```
Represents a trading instrument from OKX.

### MarkPrice
```go
type MarkPrice struct {
    InstID string
    MarkPx string
    TS     string
    Extra  map[string]interface{}
}
```
Represents mark price data for an instrument.

### MatchingSymbol
```go
type MatchingSymbol struct {
    BaseSymbol string
    Margin     Instrument
    Swap       Instrument
}
```
A pair of margin and swap instruments for the same base symbol.

### DiffResult
```go
type DiffResult struct {
    BaseSymbol      string
    MarginMarkPx    float64
    SwapMarkPx      float64
    PercentDiff     float64
    ActualDiff      float64
    IsContango      bool
    TermStructure   string
}
```
Result of a mark price difference calculation.

## API Reference

### internal/okxapi.go
- `NewHTTPClient(config Config) *HTTPClient`  
  Create a new HTTP client for OKX API.
- `(h *HTTPClient) MakeRequest(ctx context.Context, url string) ([]byte, error)`  
  Make a GET request with proper headers.
- `(h *HTTPClient) FetchMarkPrices(ctx context.Context, instType string) (map[string]MarkPrice, error)`  
  Fetch mark prices for a given instrument type.
- `(h *HTTPClient) FetchInstruments(ctx context.Context, instType, quoteCcy string) ([]Instrument, error)`  
  Fetch instruments for a given type and quote currency.

### internal/analyzer.go
- `FuseData(instruments []Instrument, markPrices map[string]MarkPrice) []Instrument`  
  Combine instrument data with mark price data.
- `ExtractBaseSymbol(instID string) string`  
  Extract the base symbol from an instrument ID.
- `FindMatchingSymbols(marginInstruments, swapInstruments []Instrument) []MatchingSymbol`  
  Find symbols that exist in both margin and swap instruments.
- `ParseFloat(s string) (float64, error)`  
  Safely parse a string to float64.
- `CalculateTopMarkPxDiffs(matches []MatchingSymbol, topN int, minDiff float64) ([]DiffResult, error)`  
  Calculate and return the top mark price differences.
- `PrintTopMarkPxDiffs(diffs []DiffResult, minDiff float64)`  
  Print the top mark price differences in a formatted table.

### internal/storage.go
- `SaveToFile(data interface{}, filename string) error`  
  Save data to a JSON file.

## Quickstart

```sh
# Build the main binary
cd okxauto
go build ./cmd/getinsts.go

# Run with default parameters
./getinsts

# Example: Show top 5 symbols with at least 0.2% mark price diff
./getinsts -top 5 -min-diff 0.2
```

## Requirements
- Go 1.18+
- Internet connection (for OKX API)

## Output
- Results are saved to `okx_matching_symbols_margin_swap.json` by default.
- Console output shows the top mark price differences.

## Extending
- Add new commands in `cmd/`
- Add new business logic in `internal/`

---
MIT License 
