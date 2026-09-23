package collectors

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
)

func TestParallelPriceClient_Pagination(t *testing.T) {
	var requestCount int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count := atomic.AddInt32(&requestCount, 1)
		w.Header().Set("Content-Type", "application/json")

		if count == 1 {
			// First page: returns 2 items and a NextPageLink pointing to page 2
			resp := PriceResult{
				Items: []map[string]interface{}{
					{"armSkuName": "Standard_D2s_v3", "retailPrice": 0.096},
					{"armSkuName": "Standard_D4s_v3", "retailPrice": 0.192},
				},
				NextPageLink: "http://" + r.Host + "/page2",
				Count:        2,
			}
			json.NewEncoder(w).Encode(resp)
		} else {
			// Second page: returns 1 item and no NextPageLink
			resp := PriceResult{
				Items: []map[string]interface{}{
					{"armSkuName": "Standard_D8s_v3", "retailPrice": 0.384},
				},
				NextPageLink: "",
				Count:        1,
			}
			json.NewEncoder(w).Encode(resp)
		}
	}))
	defer server.Close()

	client := NewParallelPriceClient(2)
	client.baseURL = server.URL

	prices, err := client.fetchPricesWithFilter("serviceName eq 'Virtual Machines'", 5)
	if err != nil {
		t.Fatalf("fetchPricesWithFilter failed: %v", err)
	}

	if len(prices) != 3 {
		t.Fatalf("expected 3 total items across 2 pages, got %d", len(prices))
	}
	if atomic.LoadInt32(&requestCount) != 2 {
		t.Fatalf("expected 2 HTTP requests (page 1 + page 2), got %d", requestCount)
	}
}

func TestParallelPriceClient_MaxPagesEnforced(t *testing.T) {
	var requestCount int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&requestCount, 1)
		w.Header().Set("Content-Type", "application/json")
		// Infinite stream of pages
		resp := PriceResult{
			Items: []map[string]interface{}{
				{"armSkuName": "Standard_B1s", "retailPrice": 0.0104},
			},
			NextPageLink: "http://" + r.Host + "/next",
			Count:        1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewParallelPriceClient(2)
	client.baseURL = server.URL

	// Ask for max 2 pages
	prices, err := client.fetchPricesWithFilter("serviceName eq 'Virtual Machines'", 2)
	if err != nil {
		t.Fatalf("fetchPricesWithFilter failed: %v", err)
	}

	if len(prices) != 2 {
		t.Fatalf("expected 2 items capped by maxPages=2, got %d", len(prices))
	}
	if atomic.LoadInt32(&requestCount) != 2 {
		t.Fatalf("expected exactly 2 requests, got %d", requestCount)
	}
}

func TestParallelPriceClient_RetryAfter429(t *testing.T) {
	var attempts int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempt := atomic.AddInt32(&attempts, 1)
		if attempt == 1 {
			w.Header().Set("Retry-After", "1")
			w.WriteHeader(http.StatusTooManyRequests)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		resp := PriceResult{
			Items: []map[string]interface{}{
				{"armSkuName": "Standard_D2s_v3", "retailPrice": 0.096},
			},
			Count: 1,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	client := NewParallelPriceClient(1)
	resp, err := client.getWithRetry(server.URL)
	if err != nil {
		t.Fatalf("getWithRetry failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200 after retry, got %d", resp.StatusCode)
	}
	if atomic.LoadInt32(&attempts) != 2 {
		t.Fatalf("expected 2 attempts (initial 429 + retry 200), got %d", attempts)
	}
}
