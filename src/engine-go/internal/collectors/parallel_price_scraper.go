package collectors

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"sync"
	"time"

	"golang.org/x/time/rate"
)

// AzureRetailServiceNames matches the Python list of Azure services
var AzureRetailServiceNames = []string{
	"Virtual Machines",
	"Virtual Machines Licenses",
	"Azure Kubernetes Service",
	"Container Instances",
	"App Service",
	"Functions",
	"Storage",
	"Archive Storage",
	"Azure NetApp Files",
	"Virtual Network",
	"VPN Gateway",
	"ExpressRoute",
	"Azure Front Door Service",
	"Bandwidth",
	"Load Balancer",
	"NAT Gateway",
	"SQL Database",
	"Azure Cosmos DB",
	"Azure Database for PostgreSQL",
	"Azure Database for MySQL",
	"Cache for Redis",
	"Azure Monitor",
	"Log Analytics",
	"Key Vault",
	"Microsoft Defender for Cloud",
}

// PriceResult represents a single price item from the Azure Retail Prices API
type PriceResult struct {
	Items        []map[string]interface{} `json:"Items"`
	NextPageLink string                   `json:"NextPageLink"`
	Count        int                      `json:"Count"`
}

// ServicePriceResult contains the results for a single service
type ServicePriceResult struct {
	ServiceName string
	Prices      []map[string]interface{}
	Error       error
}

// ParallelPriceClient handles parallel price scraping with rate limiting
type ParallelPriceClient struct {
	baseURL    string
	currency   string
	httpClient *http.Client
	limiter    *rate.Limiter
	concurrency int
}

// NewParallelPriceClient creates a new parallel price client
func NewParallelPriceClient(concurrency int) *ParallelPriceClient {
	// Rate limiter: 10 requests per second with burst of 10
	limiter := rate.NewLimiter(rate.Every(time.Second/10), 10)
	
	return &ParallelPriceClient{
		baseURL:     "https://prices.azure.com/api/retail/prices",
		currency:    "USD",
		httpClient:  &http.Client{Timeout: 30 * time.Second},
		limiter:     limiter,
		concurrency: concurrency,
	}
}

// ParallelServiceScrape fetches pricing data for multiple services in parallel
func (p *ParallelPriceClient) ParallelServiceScrape(services []string) []map[string]interface{} {
	if len(services) == 0 {
		services = AzureRetailServiceNames
	}

	results := make([]map[string]interface{}, 0)
	resultChan := make(chan ServicePriceResult, len(services))
	
	// Use semaphore pattern to limit concurrency
	semaphore := make(chan struct{}, p.concurrency)
	var wg sync.WaitGroup

	for _, service := range services {
		wg.Add(1)
		go func(svc string) {
			defer wg.Done()
			
			// Acquire semaphore
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			// Fetch pricing data for specific service
			prices, err := p.fetchServicePrices(svc, 2) // Limit to 2 pages per service for performance
			resultChan <- ServicePriceResult{
				ServiceName: svc,
				Prices:      prices,
				Error:       err,
			}
		}(service)
	}

	// Wait for all goroutines to complete
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	for result := range resultChan {
		if result.Error != nil {
			fmt.Printf("Error fetching prices for service %s: %v\n", result.ServiceName, result.Error)
			continue
		}
		results = append(results, result.Prices...)
	}

	return results
}

// getWithRetry executes an HTTP GET request with rate limiting and Retry-After backoff on HTTP 429.
func (p *ParallelPriceClient) getWithRetry(url string) (*http.Response, error) {
	maxRetries := 3
	for attempt := 0; attempt < maxRetries; attempt++ {
		if err := p.limiter.Wait(context.Background()); err != nil {
			return nil, fmt.Errorf("rate limiter error: %w", err)
		}

		resp, err := p.httpClient.Get(url)
		if err != nil {
			return nil, fmt.Errorf("HTTP request failed: %w", err)
		}

		if resp.StatusCode == http.StatusTooManyRequests {
			retryAfterStr := resp.Header.Get("Retry-After")
			resp.Body.Close()
			waitSeconds := 2 * (attempt + 1)
			if retryAfterStr != "" {
				if sec, parseErr := strconv.Atoi(retryAfterStr); parseErr == nil && sec > 0 {
					waitSeconds = sec
				}
			}
			time.Sleep(time.Duration(waitSeconds) * time.Second)
			continue
		}

		return resp, nil
	}
	return nil, fmt.Errorf("exceeded max retries for %s", url)
}

// fetchServicePrices fetches pricing data for a specific service with pagination
func (p *ParallelPriceClient) fetchServicePrices(serviceName string, maxPages int) ([]map[string]interface{}, error) {
	filter := fmt.Sprintf("serviceName eq '%s' and priceType eq 'Consumption'", serviceName)
	params := url.Values{}
	params.Set("currencyCode", p.currency)
	params.Set("$filter", filter)

	baseURL := fmt.Sprintf("%s?%s", p.baseURL, params.Encode())
	
	var allPrices []map[string]interface{}
	currentURL := baseURL
	pageCount := 0

	for currentURL != "" {
		resp, err := p.getWithRetry(currentURL)
		if err != nil {
			return nil, err
		}

		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			return nil, fmt.Errorf("HTTP error: %s", resp.Status)
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, fmt.Errorf("failed to read response body: %w", err)
		}

		var result PriceResult
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse JSON: %w", err)
		}

		allPrices = append(allPrices, result.Items...)
		pageCount++

		// Check if we've reached the max pages limit
		if maxPages > 0 && pageCount >= maxPages {
			break
		}

		// Follow the NextPageLink returned by Azure Retail Prices API
		currentURL = result.NextPageLink
	}

	return allPrices, nil
}

// GetCatalogPrices fetches all Azure retail prices with aggressive parallelization
func (p *ParallelPriceClient) GetCatalogPrices() []map[string]interface{} {
	return p.ParallelServiceScrape(AzureRetailServiceNames)
}

// GetPricesByRegion fetches prices for specific services in a region
func (p *ParallelPriceClient) GetPricesByRegion(services []string, region string) []map[string]interface{} {
	results := make([]map[string]interface{}, 0)
	resultChan := make(chan ServicePriceResult, len(services))
	
	semaphore := make(chan struct{}, p.concurrency)
	var wg sync.WaitGroup

	for _, service := range services {
		wg.Add(1)
		go func(svc string) {
			defer wg.Done()
			
			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			filter := fmt.Sprintf("serviceName eq '%s' and priceType eq 'Consumption' and armRegionName eq '%s'", svc, region)
			prices, err := p.fetchPricesWithFilter(filter, 2)
			resultChan <- ServicePriceResult{
				ServiceName: svc,
				Prices:      prices,
				Error:       err,
			}
		}(service)
	}

	go func() {
		wg.Wait()
		close(resultChan)
	}()

	for result := range resultChan {
		if result.Error != nil {
			fmt.Printf("Error fetching prices for service %s in region %s: %v\n", result.ServiceName, region, result.Error)
			continue
		}
		results = append(results, result.Prices...)
	}

	return results
}

// fetchPricesWithFilter fetches prices using a custom filter
func (p *ParallelPriceClient) fetchPricesWithFilter(filter string, maxPages int) ([]map[string]interface{}, error) {
	params := url.Values{}
	params.Set("currencyCode", p.currency)
	params.Set("$filter", filter)

	baseURL := fmt.Sprintf("%s?%s", p.baseURL, params.Encode())
	
	var allPrices []map[string]interface{}
	currentURL := baseURL
	pageCount := 0

	for currentURL != "" {
		resp, err := p.getWithRetry(currentURL)
		if err != nil {
			return nil, err
		}

		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			return nil, fmt.Errorf("HTTP error: %s", resp.Status)
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, fmt.Errorf("failed to read response body: %w", err)
		}

		var result PriceResult
		if err := json.Unmarshal(body, &result); err != nil {
			return nil, fmt.Errorf("failed to parse JSON: %w", err)
		}

		allPrices = append(allPrices, result.Items...)
		pageCount++

		if maxPages > 0 && pageCount >= maxPages {
			break
		}

		currentURL = result.NextPageLink
	}

	return allPrices, nil
}

// SetConcurrency updates the concurrency level
func (p *ParallelPriceClient) SetConcurrency(concurrency int) {
	p.concurrency = concurrency
}

// SetRateLimit updates the rate limiter
func (p *ParallelPriceClient) SetRateLimit(requestsPerSecond int) {
	p.limiter = rate.NewLimiter(rate.Every(time.Second/time.Duration(requestsPerSecond)), requestsPerSecond)
}