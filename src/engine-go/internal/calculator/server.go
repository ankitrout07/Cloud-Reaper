package calculator

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
)

// Global calculator instance
var (
	globalCalculator *CostCalculator
	calcInit         sync.Once
)

// GetCalculator returns the singleton calculator instance
func GetCalculator() *CostCalculator {
	calcInit.Do(func() {
		globalCalculator = NewCostCalculator()
		log.Println("[Calculator] Initialized cost calculator")
	})
	return globalCalculator
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// MonthlyCostRequest represents a monthly cost calculation request
type MonthlyCostRequest struct {
	Provider     string  `json:"provider"`
	ResourceType string  `json:"resource_type"`
	SKU          string  `json:"sku"`
	Quantity     float64 `json:"quantity"`
}

// HourlyCostRequest represents an hourly cost calculation request
type HourlyCostRequest struct {
	Provider     string  `json:"provider"`
	ResourceType string  `json:"resource_type"`
	SKU          string  `json:"sku"`
	Quantity     float64 `json:"quantity"`
}

// BatchCostRequest represents a batch cost calculation request
type BatchCostRequest struct {
	Items []BurnItem `json:"items"`
}

// PriceUpdateRequest represents a price update request
type PriceUpdateRequest struct {
	Provider     string  `json:"provider"`
	ResourceType string  `json:"resource_type"`
	SKU          string  `json:"sku"`
	Rate         float64 `json:"rate"`
}

// RegisterCalculatorHandlers registers HTTP handlers for cost calculator
func RegisterCalculatorHandlers(mux *http.ServeMux) {
	calc := GetCalculator()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{
			"status":  "healthy",
			"service": "cost_calculator",
		})
	})

	// Calculate monthly cost
	mux.HandleFunc("/api/calculator/monthly", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req MonthlyCostRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		cost := calc.CalculateMonthlyCost(req.Provider, req.ResourceType, req.SKU, req.Quantity)

		sendJSONResponse(w, map[string]interface{}{
			"cost":      cost,
			"currency":  calc.GetCurrency(),
			"formatted": calc.FormatPrice(cost),
		})
	})

	// Calculate hourly cost
	mux.HandleFunc("/api/calculator/hourly", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req HourlyCostRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		cost := calc.CalculateHourlyCost(req.Provider, req.ResourceType, req.SKU, req.Quantity)

		sendJSONResponse(w, map[string]interface{}{
			"cost":      cost,
			"currency":  calc.GetCurrency(),
			"formatted": calc.FormatPrice(cost),
		})
	})

	// Calculate total hourly burn (batch)
	mux.HandleFunc("/api/calculator/total_burn", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchCostRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		total := calc.CalculateTotalHourlyBurn(req.Items)

		sendJSONResponse(w, map[string]interface{}{
			"total_hourly_burn": total,
			"currency":          calc.GetCurrency(),
			"formatted":         calc.FormatPrice(total),
			"item_count":        len(req.Items),
		})
	})

	// Batch monthly cost calculation
	mux.HandleFunc("/api/calculator/batch_monthly", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchCostRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		results := calc.BatchCalculateMonthlyCost(req.Items)

		sendJSONResponse(w, map[string]interface{}{
			"results":    results,
			"item_count": len(req.Items),
			"currency":   calc.GetCurrency(),
		})
	})

	// Batch hourly cost calculation
	mux.HandleFunc("/api/calculator/batch_hourly", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req BatchCostRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		results := calc.BatchCalculateHourlyCost(req.Items)

		sendJSONResponse(w, map[string]interface{}{
			"results":    results,
			"item_count": len(req.Items),
			"currency":   calc.GetCurrency(),
		})
	})

	// Update price
	mux.HandleFunc("/api/calculator/update_price", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req PriceUpdateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if err := calc.UpdatePrice(req.Provider, req.ResourceType, req.SKU, req.Rate); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]string{
			"status": "updated",
		})
	})

	// Load price book
	mux.HandleFunc("/api/calculator/load_pricebook", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var bookData map[string]interface{}
		if err := json.NewDecoder(r.Body).Decode(&bookData); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		data, err := json.Marshal(bookData)
		if err != nil {
			sendJSONError(w, "Failed to marshal price book", http.StatusInternalServerError)
			return
		}

		if err := calc.LoadPriceBook(data); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]string{
			"status": "loaded",
		})
	})

	// Set currency
	mux.HandleFunc("/api/calculator/set_currency", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			Currency string `json:"currency"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		calc.SetCurrency(req.Currency)

		sendJSONResponse(w, map[string]string{
			"currency": calc.GetCurrency(),
		})
	})

	// Get statistics
	mux.HandleFunc("/api/calculator/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		book := calc.GetPriceBook()
		providerCount := len(book.Providers)

		totalResourceTypes := 0
		totalSKUs := 0
		for _, provider := range book.Providers {
			totalResourceTypes += len(provider.ResourceTypes)
			for _, resourceType := range provider.ResourceTypes {
				totalSKUs += len(resourceType)
			}
		}

		sendJSONResponse(w, map[string]interface{}{
			"providers":      providerCount,
			"resource_types": totalResourceTypes,
			"total_skus":     totalSKUs,
			"currency":       calc.GetCurrency(),
		})
	})
}

// Helper functions for HTTP responses
func sendJSONResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: true,
		Data:    data,
	})
}

func sendJSONError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: false,
		Error:   message,
	})
}

// StartCalculatorServer starts the cost calculator HTTP server
func StartCalculatorServer(port int) error {
	mux := http.NewServeMux()
	RegisterCalculatorHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting cost calculator server on %s", addr)
	return http.ListenAndServe(addr, mux)
}
