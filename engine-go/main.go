package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"sync"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
)

type VMReport struct {
	Name       string  `json:"name"`
	Usage      float64 `json:"usage"`
	ResourceID string  `json:"id"`
}

type AzurePriceResult struct {
	Items        []map[string]interface{} `json:"Items"`
	NextPageLink string                   `json:"NextPageLink"`
}

type ScanResult struct {
	OrphanedDisks []string                 `json:"orphaned_disks"`
	ActiveVMs     []string                 `json:"active_vms"`
	VMReports     []VMReport               `json:"vm_reports"`
	Prices        []map[string]interface{} `json:"prices,omitempty"`
}

func fetchAllPrices(serviceName string, wg *sync.WaitGroup, mu *sync.Mutex, result *ScanResult) {
	defer wg.Done()

	filter := fmt.Sprintf("serviceName eq '%s'", serviceName)
	baseURL := fmt.Sprintf("https://prices.azure.com/api/retail/prices?currencyCode=USD&$filter=%s", url.QueryEscape(filter))

	for baseURL != "" {
		resp, err := http.Get(baseURL)
		if err != nil {
			return
		}

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			resp.Body.Close()
			return
		}
		
		var priceResult AzurePriceResult
		if err := json.Unmarshal(body, &priceResult); err != nil {
			resp.Body.Close()
			return
		}

		mu.Lock()
		result.Prices = append(result.Prices, priceResult.Items...)
		mu.Unlock()

		baseURL = priceResult.NextPageLink // Follow pagination
		resp.Body.Close()
	}
}

func main() {
	subscriptionID := os.Getenv("AZURE_SUBSCRIPTION_ID")
	if subscriptionID == "" {
		log.Fatal("AZURE_SUBSCRIPTION_ID not set")
	}

	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		log.Fatal(err)
	}

	ctx := context.Background()
	var wg sync.WaitGroup
	result := &ScanResult{
		OrphanedDisks: []string{},
		ActiveVMs:     []string{},
		VMReports:     []VMReport{},
		Prices:        []map[string]interface{}{},
	}
	mu := &sync.Mutex{}

	// Task 1: Scan for Orphaned Disks
	wg.Add(1)
	go func() {
		defer wg.Done()
		client, err := armcompute.NewDisksClient(subscriptionID, cred, nil)
		if err != nil {
			return
		}
		pager := client.NewListPager(nil)
		for pager.More() {
			page, err := pager.NextPage(ctx)
			if err != nil {
				break
			}
			for _, disk := range page.Value {
				if disk.ManagedBy == nil {
					mu.Lock()
					result.OrphanedDisks = append(result.OrphanedDisks, *disk.Name)
					mu.Unlock()
				}
			}
		}
	}()

	// Task 2: Scan for VMs and their Metrics
	wg.Add(1)
	go func() {
		defer wg.Done()
		vmClient, err := armcompute.NewVirtualMachinesClient(subscriptionID, cred, nil)
		if err != nil {
			return
		}
		monitorClient, err := armmonitor.NewMetricsClient(subscriptionID, cred, nil)
		if err != nil {
			return
		}

		pager := vmClient.NewListAllPager(nil)
		var vms []*armcompute.VirtualMachine
		for pager.More() {
			page, err := pager.NextPage(ctx)
			if err != nil {
				break
			}
			vms = append(vms, page.Value...)
		}

		// Fetch metrics in parallel
		var metricWg sync.WaitGroup
		reportChan := make(chan VMReport, len(vms))

		startTime := time.Now().Add(-1 * time.Hour).Format(time.RFC3339)
		endTime := time.Now().Format(time.RFC3339)
		timespan := fmt.Sprintf("%s/%s", startTime, endTime)

		for _, vm := range vms {
			mu.Lock()
			result.ActiveVMs = append(result.ActiveVMs, *vm.Name)
			mu.Unlock()

			metricWg.Add(1)
			go func(vm *armcompute.VirtualMachine) {
				defer metricWg.Done()

				res, err := monitorClient.List(ctx, *vm.ID, &armmonitor.MetricsClientListOptions{
					Timespan:    &timespan,
					Interval:    ptr("PT1H"),
					Metricnames: ptr("Percentage CPU"),
					Aggregation: ptr("Average"),
				})

				usage := 0.0
				if err == nil && len(res.Value) > 0 && len(res.Value[0].Timeseries) > 0 {
					data := res.Value[0].Timeseries[0].Data
					if len(data) > 0 && data[0].Average != nil {
						usage = *data[0].Average
					}
				}

				reportChan <- VMReport{
					Name:       *vm.Name,
					Usage:      usage,
					ResourceID: *vm.ID,
				}
			}(vm)
		}

		metricWg.Wait()
		close(reportChan)

		for r := range reportChan {
			mu.Lock()
			result.VMReports = append(result.VMReports, r)
			mu.Unlock()
		}
	}()

	// Task 3: Fetch Live Prices for key services
	myResources := []string{"Virtual Machines", "Storage", "Networking"}
	for _, resource := range myResources {
		wg.Add(1)
		go fetchAllPrices(resource, &wg, mu, result)
	}

	wg.Wait()

	// Output result as JSON for Python to ingest
	output, _ := json.Marshal(result)
	fmt.Println(string(output))
}

func ptr[T any](v T) *T {
	return &v
}
