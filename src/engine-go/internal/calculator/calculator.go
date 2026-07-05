package calculator

import (
	"encoding/json"
	"fmt"
	"math"
	"sync"
)

// PriceBook represents the pricing structure for cloud providers
type PriceBook struct {
	Providers map[string]Provider `json:"providers"`
}

// Provider represents cloud provider pricing
type Provider struct {
	ResourceTypes map[string]ResourceType `json:"resource_types"`
}

// ResourceType represents pricing for a specific resource type
type ResourceType map[string]float64 // SKU -> Rate

// BurnItem represents a cost calculation item
type BurnItem struct {
	Provider     string  `json:"provider"`
	ResourceType string  `json:"resource_type"`
	SKU          string  `json:"sku"`
	Quantity     float64 `json:"quantity"`
	Frequency    string  `json:"frequency"` // "hourly" or "monthly"
}

// CostCalculator handles cost calculations with batch operations
type CostCalculator struct {
	priceBook   *PriceBook
	priceBookMu sync.RWMutex
	currency    string
}

// NewCostCalculator creates a new cost calculator
func NewCostCalculator() *CostCalculator {
	return &CostCalculator{
		priceBook: &PriceBook{
			Providers: make(map[string]Provider),
		},
		currency: "USD",
	}
}

// LoadPriceBook loads pricing data from JSON
func (cc *CostCalculator) LoadPriceBook(data []byte) error {
	cc.priceBookMu.Lock()
	defer cc.priceBookMu.Unlock()

	var book PriceBook
	if err := json.Unmarshal(data, &book); err != nil {
		return fmt.Errorf("failed to parse price book: %w", err)
	}

	cc.priceBook = &book
	return nil
}

// GetPriceBook returns the current price book
func (cc *CostCalculator) GetPriceBook() *PriceBook {
	cc.priceBookMu.RLock()
	defer cc.priceBookMu.RUnlock()
	return cc.priceBook
}

// CalculateMonthlyCost calculates monthly cost for a single SKU
func (cc *CostCalculator) CalculateMonthlyCost(provider, resourceType, sku string, quantity float64) float64 {
	cc.priceBookMu.RLock()
	defer cc.priceBookMu.RUnlock()

	rate, err := cc.getRate(provider, resourceType, sku)
	if err != nil {
		return 0.0
	}

	// Storage is typically per GB per month
	if resourceType == "ebs" || resourceType == "disk" || resourceType == "storage" {
		return rate * quantity
	}

	// Compute instances are hourly (730 hours per month)
	return rate * 730 * quantity
}

// CalculateHourlyCost calculates hourly cost for a single SKU
func (cc *CostCalculator) CalculateHourlyCost(provider, resourceType, sku string, quantity float64) float64 {
	cc.priceBookMu.RLock()
	defer cc.priceBookMu.RUnlock()

	rate, err := cc.getRate(provider, resourceType, sku)
	if err != nil {
		return 0.0
	}

	// Storage is monthly, convert to hourly
	if resourceType == "ebs" || resourceType == "disk" || resourceType == "storage" {
		return (rate * quantity) / 730
	}

	// Compute instances are hourly
	return rate * quantity
}

// getRate retrieves the rate for a specific SKU
func (cc *CostCalculator) getRate(provider, resourceType, sku string) (float64, error) {
	prov, ok := cc.priceBook.Providers[provider]
	if !ok {
		return 0, fmt.Errorf("provider %s not found", provider)
	}

	resType, ok := prov.ResourceTypes[resourceType]
	if !ok {
		return 0, fmt.Errorf("resource type %s not found for provider %s", resourceType, provider)
	}

	rate, ok := resType[sku]
	if !ok {
		return 0, fmt.Errorf("SKU %s not found for %s/%s", sku, provider, resourceType)
	}

	return rate, nil
}

// CalculateTotalHourlyBurn calculates total hourly burn rate for multiple items
// This uses concurrent processing for improved performance
func (cc *CostCalculator) CalculateTotalHourlyBurn(items []BurnItem) float64 {
	if len(items) == 0 {
		return 0.0
	}

	// Use worker pool for concurrent calculations
	numWorkers := min(10, len(items))
	jobs := make(chan BurnItem, len(items))
	results := make(chan float64, len(items))

	// Start workers
	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range jobs {
				hourlyCost := cc.calculateItemHourlyCost(item)
				results <- hourlyCost
			}
		}()
	}

	// Send jobs
	for _, item := range items {
		jobs <- item
	}
	close(jobs)

	// Wait for workers to complete
	wg.Wait()
	close(results)

	// Sum results
	total := 0.0
	for result := range results {
		total += result
	}

	return roundToPrecision(total, 6)
}

// calculateItemHourlyCost calculates hourly cost for a single item
func (cc *CostCalculator) calculateItemHourlyCost(item BurnItem) float64 {
	// Set defaults using local variables to avoid confusion
	quantity := item.Quantity
	if quantity == 0 {
		quantity = 1
	}
	
	frequency := item.Frequency
	if frequency == "" {
		frequency = "hourly"
	}

	if frequency == "monthly" {
		monthlyCost := cc.CalculateMonthlyCost(item.Provider, item.ResourceType, item.SKU, quantity)
		return monthlyCost / 730
	}

	return cc.CalculateHourlyCost(item.Provider, item.ResourceType, item.SKU, quantity)
}

// BatchCalculateMonthlyCost performs batch monthly cost calculations
func (cc *CostCalculator) BatchCalculateMonthlyCost(items []BurnItem) []float64 {
	results := make([]float64, len(items))

	var wg sync.WaitGroup
	var resultsMu sync.Mutex
	
	for i, item := range items {
		wg.Add(1)
		go func(idx int, burnItem BurnItem) {
			defer wg.Done()
			cost := cc.CalculateMonthlyCost(burnItem.Provider, burnItem.ResourceType, burnItem.SKU, burnItem.Quantity)
			
			// Protect results slice write with mutex
			resultsMu.Lock()
			results[idx] = cost
			resultsMu.Unlock()
		}(i, item)
	}

	wg.Wait()
	return results
}

// BatchCalculateHourlyCost performs batch hourly cost calculations
func (cc *CostCalculator) BatchCalculateHourlyCost(items []BurnItem) []float64 {
	results := make([]float64, len(items))

	var wg sync.WaitGroup
	var resultsMu sync.Mutex
	
	for i, item := range items {
		wg.Add(1)
		go func(idx int, burnItem BurnItem) {
			defer wg.Done()
			cost := cc.CalculateHourlyCost(burnItem.Provider, burnItem.ResourceType, burnItem.SKU, burnItem.Quantity)
			
			// Protect results slice write with mutex
			resultsMu.Lock()
			results[idx] = cost
			resultsMu.Unlock()
		}(i, item)
	}

	wg.Wait()
	return results
}

// UpdatePrice updates a specific price in the price book
func (cc *CostCalculator) UpdatePrice(provider, resourceType, sku string, rate float64) error {
	cc.priceBookMu.Lock()
	defer cc.priceBookMu.Unlock()

	prov, ok := cc.priceBook.Providers[provider]
	if !ok {
		prov = Provider{
			ResourceTypes: make(map[string]ResourceType),
		}
		cc.priceBook.Providers[provider] = prov
	}

	resType, ok := prov.ResourceTypes[resourceType]
	if !ok {
		resType = make(ResourceType)
		prov.ResourceTypes[resourceType] = resType
	}

	resType[sku] = rate
	return nil
}

// SetCurrency sets the currency for cost calculations
func (cc *CostCalculator) SetCurrency(currency string) {
	cc.currency = currency
}

// GetCurrency returns the current currency
func (cc *CostCalculator) GetCurrency() string {
	return cc.currency
}

// FormatPrice formats a float as a currency string
func (cc *CostCalculator) FormatPrice(amount float64) string {
	symbol := "$"
	if cc.currency == "EUR" {
		symbol = "€"
	} else if cc.currency == "GBP" {
		symbol = "£"
	} else if cc.currency == "JPY" {
		symbol = "¥"
	}
	return fmt.Sprintf("%s%.2f", symbol, amount)
}

// roundToPrecision rounds a float to specified decimal places
func roundToPrecision(value float64, precision int) float64 {
	multiplier := math.Pow(10, float64(precision))
	return math.Round(value*multiplier) / multiplier
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
