//go:build cli

package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"
	"sync"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/resources/armsubscriptions"

	"cloud-reaper/engine-go/internal/arbitrage"
	"cloud-reaper/engine-go/internal/bridge"
	"cloud-reaper/engine-go/internal/collectors"
	"cloud-reaper/engine-go/internal/db"
)

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

type scanResult struct {
	UserName         string             `json:"user_name"`
	SubscriptionName string             `json:"subscription_name"`
	OrphanedDisks    []orphanedResource `json:"orphaned_disks"`
	OrphanedSnaps    []orphanedResource `json:"orphaned_snapshots"`
	ActiveVMs        []string           `json:"active_vms"`
	VMReports        []vmReport         `json:"vm_reports"`
	Prices           []map[string]any   `json:"prices,omitempty"`
}

func main() {
	subscription := flag.String("subscription", "", "Azure subscription ID")
	listSubs := flag.Bool("list-subs", false, "List accessible Azure subscriptions")
	mode := flag.String("mode", "scan", "Operation mode: scan, prices, arbitrage, serve")
	sku := flag.String("sku", "", "SKU for arbitrage mode")
	regions := flag.String("regions", "", "Comma-separated regions for arbitrage mode")
	provider := flag.String("provider", "azure", "Cloud provider: azure, aws, gcp")
	servePort := flag.Int("port", 7070, "Port for HTTP bridge server (serve mode)")
	flag.Parse()

	if *listSubs {
		listSubscriptions()
		return
	}

	switch *mode {
	case "arbitrage":
		if *sku == "" || *regions == "" {
			fmt.Fprintln(os.Stderr, "arbitrage mode requires --sku and --regions")
			os.Exit(1)
		}
		regionList := strings.Split(*regions, ",")
		for i := range regionList {
			regionList[i] = strings.TrimSpace(regionList[i])
		}
		arbitrage.RunArbitrageScan(*sku, regionList)
	case "prices":
		outputPrices(*provider)
	case "serve":
		// HTTP bridge server: lets Python call the Go engine non-blocking over loopback.
		// Boots in the background during bootstrap; Python calls /scan, /prices, /health.
		bridge.RunBridgeServer(*servePort)
	case "scan":
		subID := *subscription
		if subID == "" {
			subID = os.Getenv("AZURE_SUBSCRIPTION_ID")
		}
		if subID == "" {
			fmt.Fprintln(os.Stderr, "scan mode requires --subscription or AZURE_SUBSCRIPTION_ID")
			os.Exit(1)
		}
		runScan(subID)
	default:
		fmt.Fprintf(os.Stderr, "unknown mode %q (use scan, prices, arbitrage, serve)\n", *mode)
		os.Exit(1)
	}
}

func listSubscriptions() {
	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "auth error: %v\n", err)
		os.Exit(1)
	}
	client, err := armsubscriptions.NewClient(cred, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "subscription client error: %v\n", err)
		os.Exit(1)
	}
	pager := client.NewListPager(nil)
	type subEntry struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	var subs []subEntry
	for pager.More() {
		page, err := pager.NextPage(nil)
		if err != nil {
			break
		}
		for _, s := range page.Value {
			if s == nil || s.SubscriptionID == nil {
				continue
			}
			name := *s.SubscriptionID
			if s.DisplayName != nil {
				name = *s.DisplayName
			}
			subs = append(subs, subEntry{ID: *s.SubscriptionID, Name: name})
		}
	}
	out, _ := json.Marshal(subs)
	fmt.Println(string(out))
}

func runScan(subscriptionID string) {
	scraper := &collectors.AzureScraper{}
	if err := scraper.Authenticate(map[string]string{"subscription_id": subscriptionID}); err != nil {
		fmt.Fprintf(os.Stderr, "authenticate error: %v\n", err)
		os.Exit(1)
	}

	resources, err := scraper.ScanResources()
	if err != nil {
		fmt.Fprintf(os.Stderr, "scan error: %v\n", err)
		os.Exit(1)
	}

	// ── Zero-allocation persistence ──────────────────────────────────────────
	// Flush the scanned resources into SQLite via the sync.Pool-backed
	// BatchUpsert.  The pooled buffer is acquired once, filled, upserted in a
	// single transaction, then returned — the GC never touches the intermediate
	// slice.  Errors here are non-fatal: the JSON result is still emitted so
	// the Python caller can continue even when the local DB is unavailable.
	if stats, upsertErr := db.BatchUpsert(resources); upsertErr != nil {
		fmt.Fprintf(os.Stderr, "[warn] db upsert skipped: %v\n", upsertErr)
	} else {
		fmt.Fprintf(os.Stderr, "[db] BatchUpsert: %d resources in %s (pool_reused=%v)\n",
			stats.ResourceCount, stats.Elapsed, stats.PoolReused)
	}
	// ────────────────────────────────────────────────────────────────────────

	result := scanResult{
		UserName:         collectors.GetAzureUserName(),
		SubscriptionName: subscriptionID,
		OrphanedDisks:    []orphanedResource{},
		OrphanedSnaps:    []orphanedResource{},
		ActiveVMs:        []string{},
		VMReports:        []vmReport{},
	}

	for _, r := range resources {
		switch r.Type {
		case "VirtualMachine":
			result.ActiveVMs = append(result.ActiveVMs, r.Name)
			result.VMReports = append(result.VMReports, vmReport{
				Name:          r.Name,
				Size:          r.SKU,
				Usage:         r.Usage,
				UsageHistory:  []float64{r.Usage},
				ID:            r.ID,
				Tags:          r.Tags,
				IsUnallocated: r.IsUnallocated,
			})
		case "OrphanedDisk":
			result.OrphanedDisks = append(result.OrphanedDisks, orphanedResource{
				Name: r.Name,
				Tags: r.Tags,
			})
		}
	}

	out, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}

func outputPrices(provider string) {
	skus := []string{
		"Standard_B2s", "Standard_D2s_v3", "Standard_D4s_v3",
		"Standard_D4s_v5", "Standard_E4s_v3",
	}
	regions := []string{"eastus", "westus2", "westeurope"}

	type priceResult struct {
		sku    string
		region string
		price  float64
		err    error
	}

	resultChan := make(chan priceResult, len(skus)*len(regions))
	var wg sync.WaitGroup

	// Fan out price fetches in parallel
	for _, skuName := range skus {
		for _, region := range regions {
			wg.Add(1)
			go func(sku, region string) {
				defer wg.Done()
				var price float64
				var err error
				switch provider {
				case "aws":
					price, err = collectors.FetchAWSPrice(sku, region)
				case "gcp":
					price, err = collectors.FetchGCPPrice(sku, region)
				default:
					price, err = collectors.FetchAzurePrice(sku, region)
				}
				resultChan <- priceResult{sku: sku, region: region, price: price, err: err}
			}(skuName, region)
		}
	}

	// Wait for all goroutines to complete
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	var prices []map[string]any
	for result := range resultChan {
		entry := map[string]any{
			"sku":    result.sku,
			"region": result.region,
			"price":  result.price,
		}
		if result.err != nil {
			entry["error"] = result.err.Error()
		}
		prices = append(prices, entry)
	}
	out, _ := json.Marshal(map[string]any{"prices": prices})
	fmt.Println(string(out))
}
