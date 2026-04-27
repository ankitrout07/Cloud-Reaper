package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
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
	Status     string  `json:"status"`
	ResourceID string  `json:"id"`
}

func main() {
	subscriptionID := os.Getenv("AZURE_SUBSCRIPTION_ID")
	if subscriptionID == "" {
		log.Fatal("AZURE_SUBSCRIPTION_ID not set")
	}

	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		log.Fatalf("failed to obtain a credential: %v", err)
	}

	ctx := context.Background()
	vmClient, err := armcompute.NewVirtualMachinesClient(subscriptionID, cred, nil)
	if err != nil {
		log.Fatalf("failed to create vm client: %v", err)
	}

	monitorClient, err := armmonitor.NewMetricsClient(subscriptionID, cred, nil)
	if err != nil {
		log.Fatalf("failed to create monitor client: %v", err)
	}

	// 1. List all VMs
	pager := vmClient.NewListAllPager(nil)
	var vms []*armcompute.VirtualMachine
	for pager.More() {
		nextResult, err := pager.NextPage(ctx)
		if err != nil {
			log.Fatalf("failed to advance page: %v", err)
		}
		vms = append(vms, nextResult.Value...)
	}

	// 2. Fetch metrics in parallel using Goroutines
	var wg sync.WaitGroup
	reportChan := make(chan VMReport, len(vms))

	startTime := time.Now().Add(-1 * time.Hour).Format(time.RFC3339)
	endTime := time.Now().Format(time.RFC3339)
	timespan := fmt.Sprintf("%s/%s", startTime, endTime)

	for _, vm := range vms {
		wg.Add(1)
		go func(vm *armcompute.VirtualMachine) {
			defer wg.Done()
			
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

			status := "OPTIMIZED"
			if usage < 5.0 {
				status = "IDLE"
			}

			reportChan <- VMReport{
				Name:       *vm.Name,
				Usage:      usage,
				Status:     status,
				ResourceID: *vm.ID,
			}
		}(vm)
	}

	// Close channel when all workers finish
	go func() {
		wg.Wait()
		close(reportChan)
	}()

	var reports []VMReport
	for r := range reportChan {
		reports = append(reports, r)
	}

	// Output as JSON for Python to consume
	json.NewEncoder(os.Stdout).Encode(reports)
}

func ptr[T any](v T) *T {
	return &v
}
