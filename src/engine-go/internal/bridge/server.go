// Package bridge — server.go
//
// Go Engine HTTP Bridge
// ======================
// When run with --mode serve, the Go binary stays resident as an HTTP server
// on loopback (default :7070). Python calls it via httpx instead of forking a
// new process for each scan, eliminating per-request fork + exec overhead.
//
// Endpoints
// ----------
//   GET  /health          → {"status":"ok","engine":"cloud-reaper-go"}
//   POST /scan            → JSON body {"subscription_id":"…","provider":"azure"}
//                           Returns the same scanResult JSON as --mode scan.
//   GET  /prices?provider=azure
//                         → Same price list as --mode prices.
//
// Concurrency model
// ------------------
// Each POST /scan request is handled in its own goroutine. Because the Go
// runtime is already running, there is no process-spawn penalty. The
// AzureScraper and BatchUpsert calls are goroutine-safe; ResourcePool is a
// sync.Pool, so concurrent scans share the pre-allocated backing arrays.
//
// Python side
// ------------
// bootstrap.py spawns the binary with --mode serve --port 7070 once at
// startup. Subsequent calls from app_async.py use asyncio httpx:
//
//   async with httpx.AsyncClient() as client:
//       resp = await client.post("http://127.0.0.1:7070/scan",
//                               json={"subscription_id": sub_id})
//       data = resp.json()

package bridge

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"cloud-reaper/engine-go/internal/collectors"
	"cloud-reaper/engine-go/internal/db"
	"cloud-reaper/engine-go/internal/streaming"
)

// scanRequest is the POST /scan request body.
type scanRequest struct {
	SubscriptionID string `json:"subscription_id"`
	Provider       string `json:"provider"` // defaults to "azure"
}

// scanResult mirrors main_cli.go's scanResult so the JSON shape is identical.
type scanResult struct {
	UserName         string             `json:"user_name"`
	SubscriptionName string             `json:"subscription_name"`
	OrphanedDisks    []orphanedResource `json:"orphaned_disks"`
	OrphanedSnaps    []orphanedResource `json:"orphaned_snapshots"`
	ActiveVMs        []string           `json:"active_vms"`
	VMReports        []vmReport         `json:"vm_reports"`
	// Bridge-only fields
	DBStats db.BatchUpsertStats `json:"db_stats"`
}

type vmReport struct {
	Name          string            `json:"name"`
	Size          string            `json:"size"`
	Usage         float64           `json:"usage"`
	UsageHistory  []float64         `json:"usage_history"`
	NetworkIn     float64           `json:"network_in"`
	NetworkOut    float64           `json:"network_out"`
	DiskIOPS      float64           `json:"disk_iops"`
	ID            string            `json:"id"`
	Tags          map[string]string `json:"tags"`
	IsUnallocated bool              `json:"is_unallocated"`
}

type orphanedResource struct {
	Name string            `json:"name"`
	Tags map[string]string `json:"tags"`
}

// RunBridgeServer starts the HTTP bridge and blocks until the process exits.
func RunBridgeServer(port int) {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/scan", handleScan)
	mux.HandleFunc("/prices", handlePrices)
	mux.HandleFunc("/prices/parallel", handleParallelPrices)

	// Real-time streaming pipeline endpoints (/stream/*)
	// Replaces Python realtime_refresh.py threading loop with sub-ms Go workers.
	streaming.RegisterStreamHandlers(mux)

	addr := fmt.Sprintf("127.0.0.1:%d", port)
	fmt.Printf("[bridge] Go engine HTTP bridge listening on http://%s\n", addr)

	server := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  120 * time.Second,
		WriteTimeout: 300 * time.Second,
		IdleTimeout:  60 * time.Second,
	}
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		fmt.Fprintf(os.Stderr, "[bridge] fatal: %v\n", err)
		os.Exit(1)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{
		"status": "ok",
		"engine": "cloud-reaper-go",
	})
}

// handleScan runs a full cloud scan and persists via BatchUpsert in-process.
// POST /scan  body: {"subscription_id":"…","provider":"azure"}
func handleScan(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"POST required"}`, http.StatusMethodNotAllowed)
		return
	}

	var req scanRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid JSON body"}`, http.StatusBadRequest)
		return
	}

	if req.SubscriptionID == "" {
		req.SubscriptionID = os.Getenv("AZURE_SUBSCRIPTION_ID")
	}
	if req.Provider == "" {
		req.Provider = "azure"
	}

	// Validate provider
	validProviders := map[string]bool{"azure": true, "aws": true, "gcp": true}
	if !validProviders[strings.ToLower(req.Provider)] {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid provider: %s (must be azure, aws, or gcp)", req.Provider))
		return
	}

	// Validate subscription ID format (basic check)
	if req.SubscriptionID == "" || len(req.SubscriptionID) < 5 {
		writeError(w, http.StatusBadRequest, "subscription_id is required and must be at least 5 characters")
		return
	}

	scraper := &collectors.AzureScraper{}
	if err := scraper.Authenticate(map[string]string{
		"subscription_id": req.SubscriptionID,
	}); err != nil {
		writeError(w, http.StatusUnauthorized, fmt.Sprintf("authenticate: %v", err))
		return
	}

	resources, err := scraper.ScanResources()
	if err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Sprintf("scan: %v", err))
		return
	}

	// ── Zero-allocation SQLite flush ──────────────────────────────────────────
	// BatchUpsert acquires a pooled []models.Resource buffer, copies resources
	// into it, runs a single SQLite upsert transaction, then returns the buffer
	// to the pool.  Zero heap allocations in steady state.
	stats, upsertErr := db.BatchUpsert(resources)
	if upsertErr != nil {
		// Non-fatal: Python still gets the JSON payload even if DB write fails.
		fmt.Fprintf(os.Stderr, "[bridge][warn] BatchUpsert: %v\n", upsertErr)
	}
	// ─────────────────────────────────────────────────────────────────────────

	result := scanResult{
		UserName:         collectors.GetAzureUserName(),
		SubscriptionName: req.SubscriptionID,
		OrphanedDisks:    []orphanedResource{},
		OrphanedSnaps:    []orphanedResource{},
		ActiveVMs:        []string{},
		VMReports:        []vmReport{},
		DBStats:          stats,
	}

	for _, res := range resources {
		switch res.Type {
		case "VirtualMachine":
			result.ActiveVMs = append(result.ActiveVMs, res.Name)
			result.VMReports = append(result.VMReports, vmReport{
				Name:          res.Name,
				Size:          res.SKU,
				Usage:         res.Usage,
				UsageHistory:  []float64{res.Usage},
				ID:            res.ID,
				Tags:          res.Tags,
				IsUnallocated: res.IsUnallocated,
			})
		case "OrphanedDisk":
			result.OrphanedDisks = append(result.OrphanedDisks, orphanedResource{
				Name: res.Name,
				Tags: res.Tags,
			})
		}
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(result)
}

// handlePrices returns the same price list as --mode prices.
// GET /prices?provider=azure
func handlePrices(w http.ResponseWriter, r *http.Request) {
	provider := strings.ToLower(r.URL.Query().Get("provider"))
	if provider == "" {
		provider = "azure"
	}

	// Validate provider
	validProviders := map[string]bool{"azure": true, "aws": true, "gcp": true}
	if !validProviders[provider] {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid provider: %s (must be azure, aws, or gcp)", provider))
		return
	}

	skus := []string{
		"Standard_B2s", "Standard_D2s_v3", "Standard_D4s_v3",
		"Standard_D4s_v5", "Standard_E4s_v3",
	}
	regions := []string{"eastus", "westus2", "westeurope"}

	var prices []map[string]any
	for _, skuName := range skus {
		for _, region := range regions {
			var price float64
			var err error
			switch provider {
			case "aws":
				price, err = collectors.FetchAWSPrice(skuName, region)
			case "gcp":
				price, err = collectors.FetchGCPPrice(skuName, region)
			default:
				price, err = collectors.FetchAzurePrice(skuName, region)
			}
			entry := map[string]any{
				"sku":    skuName,
				"region": region,
				"price":  price,
			}
			if err != nil {
				entry["error"] = err.Error()
			}
			prices = append(prices, entry)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"prices": prices})
}

func writeError(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

// handleParallelPrices provides high-performance parallel price scraping
// POST /prices/parallel body: {"services":[...],"concurrency":10,"region":""}
func handleParallelPrices(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"POST required"}`, http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		Services   []string `json:"services"`
		Concurrency int     `json:"concurrency"`
		Region     string   `json:"region"`
	}
	
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid JSON body"}`, http.StatusBadRequest)
		return
	}

	// Set defaults
	if req.Concurrency == 0 {
		req.Concurrency = 10
	}
	if len(req.Services) == 0 {
		req.Services = collectors.AzureRetailServiceNames
	}

	// Create parallel price client
	client := collectors.NewParallelPriceClient(req.Concurrency)
	
	var prices []map[string]interface{}
	var err error
	
	if req.Region != "" {
		// Regional price fetch
		prices = client.GetPricesByRegion(req.Services, req.Region)
	} else {
		// Global catalog price fetch
		prices = client.GetCatalogPrices()
	}

	response := map[string]interface{}{
		"prices": prices,
		"count":  len(prices),
		"region": req.Region,
	}
	
	if err != nil {
		response["error"] = err.Error()
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(response)
}
