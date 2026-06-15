package arbitrage

import (
	"encoding/json"
	"fmt"
	"sync"

	"cloud-reaper/engine-go/internal/collectors"
)

type ArbitrageResult struct {
	SKU     string                `json:"sku"`
	Results []RegionalPriceResult `json:"results"`
}

type RegionalPriceResult struct {
	Region string  `json:"region"`
	Price  float64 `json:"price"`
	Error  string  `json:"error,omitempty"`
}

func RunArbitrageScan(sku string, regions []string) {
	var wg sync.WaitGroup
	results := make([]RegionalPriceResult, len(regions))
	mu := &sync.Mutex{}

	// Worker pool pattern
	concurrency := 10
	sem := make(chan struct{}, concurrency)

	for i, region := range regions {
		wg.Add(1)
		go func(idx int, r string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			price, err := collectors.FetchAzurePrice(sku, r)

			mu.Lock()
			if err != nil {
				results[idx] = RegionalPriceResult{Region: r, Error: err.Error()}
			} else {
				results[idx] = RegionalPriceResult{Region: r, Price: price}
			}
			mu.Unlock()
		}(i, region)
	}

	wg.Wait()

	finalResult := ArbitrageResult{
		SKU:     sku,
		Results: results,
	}

	output, _ := json.Marshal(finalResult)
	fmt.Println(string(output))
}
