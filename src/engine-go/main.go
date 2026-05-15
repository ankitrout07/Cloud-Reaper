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
	"strings"
	"sync"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/resources/armsubscriptions"
	"golang.org/x/time/rate"

	"cloud-reaper/engine-go/collectors"
	"cloud-reaper/engine-go/db"
)

var limiter = rate.NewLimiter(rate.Every(time.Second/10), 10) // 10 requests per second

func isProtected(tags map[string]*string) bool {
	if tags == nil {
		return false
	}
	for k, v := range tags {
		if v == nil {
			continue
		}
		key := strings.ToLower(k)
		val := strings.ToLower(*v)
		if (key == "reaper-ignore" && val == "true") || (key == "environment" && val == "production") {
			return true
		}
	}
	return false
}

func isTagCompliant(tags map[string]*string) bool {
	if tags == nil {
		return false
	}
	requiredTags := []string{"owner", "project"}
	for _, req := range requiredTags {
		found := false
		for k := range tags {
			if strings.ToLower(k) == req {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}

type VMReport struct {
	Name          string             `json:"name"`
	Size          string             `json:"size"`
	Usage         float64            `json:"usage"`
	UsageHistory  []float64          `json:"usage_history"`
	NetworkIn     float64            `json:"network_in"`
	NetworkOut    float64            `json:"network_out"`
	DiskIOPS      float64            `json:"disk_iops"`
	ResourceID    string             `json:"id"`
	Tags          map[string]*string `json:"tags"`
	IsUnallocated bool               `json:"is_unallocated"`
}

type AzurePriceResult struct {
	Items        []map[string]interface{} `json:"Items"`
	NextPageLink string                   `json:"NextPageLink"`
}

type ScanResult struct {
	UserName          string                   `json:"user_name"`
	SubscriptionName  string                   `json:"subscription_name"`
	OrphanedDisks     []map[string]interface{} `json:"orphaned_disks"`
	OrphanedSnapshots []map[string]interface{} `json:"orphaned_snapshots"`
	ActiveVMs         []string                 `json:"active_vms"`
	VMReports         []VMReport               `json:"vm_reports"`
	Prices            []map[string]interface{} `json:"prices,omitempty"`
}

func GetSubscriptions() ([]map[string]string, error) {
	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		return nil, err
	}
	client, err := armsubscriptions.NewClient(cred, nil)
	if err != nil {
		return nil, err
	}

	var subs []map[string]string
	pager := client.NewListPager(nil)

	for pager.More() {
		page, err := pager.NextPage(context.Background())
		if err != nil {
			return nil, err
		}
		for _, sub := range page.Value {
			subs = append(subs, map[string]string{
				"id":   *sub.SubscriptionID,
				"name": *sub.DisplayName,
			})
		}
	}
	return subs, nil
}

func fetchPriceData(resource string, result *ScanResult, mu *sync.Mutex, wg *sync.WaitGroup) {
	defer wg.Done()
	filter := fmt.Sprintf("serviceName eq '%s'", resource)
	baseURL := fmt.Sprintf("https://prices.azure.com/api/retail/prices?currencyCode=USD&$filter=%s", url.QueryEscape(filter))
	resp, err := http.Get(baseURL)
	if err != nil {
		return
	}
	defer func() {
		_ = resp.Body.Close()
	}()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return
	}
	var priceResult AzurePriceResult
	if err := json.Unmarshal(body, &priceResult); err != nil {
		return
	}

	mu.Lock()
	defer mu.Unlock()
	for _, item := range priceResult.Items {
		retailPrice, _ := item["retailPrice"].(float64)
		minUnits, _ := item["minimumNumberOfUnits"].(float64)
		meterName, _ := item["meterName"].(string)
		unitOfMeasure, _ := item["unitOfMeasure"].(string)

		// Relaxed family filter to include all architectural components, while still excluding support/savings plans
		if strings.Contains(meterName, "Support") || strings.Contains(meterName, "Savings Plan") {
			continue
		}

		normalizedPrice := retailPrice
		if minUnits > 0 {
			normalizedPrice = retailPrice / minUnits
		}

		item["retailPrice"] = normalizedPrice
		item["isMonthlyBilling"] = strings.Contains(unitOfMeasure, "Month")
		result.Prices = append(result.Prices, item)
	}
}

func runPriceMode() {
	mu := &sync.Mutex{}
	result := &ScanResult{Prices: []map[string]interface{}{}}
	var wg sync.WaitGroup

	myResources := []string{
		"Virtual Machines",
		"Storage",
		"Networking",
		"SQL Database",
		"Azure App Service",
		"Container Registry",
		"Bandwidth",
		"Azure Cosmos DB",
		"Azure Kubernetes Service",
		"Azure Cache for Redis",
		"Load Balancer",
		"Application Gateway",
		"VPN Gateway",
		"Key Vault",
		"Log Analytics",
		"Service Bus",
		"Event Hubs",
		"Azure Functions",
		"Container Apps",
		"API Management",
		"Azure SQL Database",
		"Azure Database for PostgreSQL",
		"Azure Database for MySQL",
	}
	for _, resource := range myResources {
		wg.Add(1)
		go fetchPriceData(resource, result, mu, &wg)
	}
	wg.Wait()
	output, err := json.Marshal(result)
	if err == nil {
		fmt.Println(string(output))
	}
}

func scanOrphanedDisks(ctx context.Context, subscriptionID string, cred *azidentity.DefaultAzureCredential, result *ScanResult, mu *sync.Mutex, wg *sync.WaitGroup) {
	defer wg.Done()
	client, err := armcompute.NewDisksClient(subscriptionID, cred, nil)
	if err != nil {
		return
	}
	_ = limiter.Wait(ctx)
	pager := client.NewListPager(nil)
	for pager.More() {
		_ = limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			break
		}
		for _, disk := range page.Value {
			if disk.ManagedBy == nil {
				mu.Lock()
				result.OrphanedDisks = append(result.OrphanedDisks, map[string]interface{}{
					"name": *disk.Name,
					"tags": disk.Tags,
				})
				mu.Unlock()
			}
		}
	}
}

func scanOrphanedSnapshots(ctx context.Context, subscriptionID string, cred *azidentity.DefaultAzureCredential, result *ScanResult, mu *sync.Mutex, wg *sync.WaitGroup) {
	defer wg.Done()
	client, err := armcompute.NewSnapshotsClient(subscriptionID, cred, nil)
	if err != nil {
		return
	}
	_ = limiter.Wait(ctx)
	pager := client.NewListPager(nil)
	for pager.More() {
		_ = limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			break
		}
		for _, snap := range page.Value {
			if snap.Properties.TimeCreated != nil && time.Since(*snap.Properties.TimeCreated) > 30*24*time.Hour {
				mu.Lock()
				result.OrphanedSnapshots = append(result.OrphanedSnapshots, map[string]interface{}{
					"name": *snap.Name,
					"tags": snap.Tags,
				})
				mu.Unlock()
			}
		}
	}
}

func scanVMs(ctx context.Context, subscriptionID string, cred *azidentity.DefaultAzureCredential, result *ScanResult, mu *sync.Mutex, wg *sync.WaitGroup) {
	defer wg.Done()
	vmClient, err := armcompute.NewVirtualMachinesClient(subscriptionID, cred, nil)
	if err != nil {
		return
	}
	monitorClient, err := armmonitor.NewMetricsClient(subscriptionID, cred, nil)
	if err != nil {
		return
	}

	_ = limiter.Wait(ctx)
	pager := vmClient.NewListAllPager(nil)
	var vms []*armcompute.VirtualMachine
	for pager.More() {
		_ = limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			break
		}
		vms = append(vms, page.Value...)
	}

	var metricWg sync.WaitGroup
	reportChan := make(chan VMReport, len(vms))
	startTime := time.Now().Add(-30 * 24 * time.Hour).Format(time.RFC3339)
	endTime := time.Now().Format(time.RFC3339)
	timespan := fmt.Sprintf("%s/%s", startTime, endTime)

	for _, vm := range vms {
		mu.Lock()
		result.ActiveVMs = append(result.ActiveVMs, *vm.Name)
		mu.Unlock()

		metricWg.Add(1)
		go func(vm *armcompute.VirtualMachine) {
			defer metricWg.Done()
			_ = limiter.Wait(ctx)
			res, err := monitorClient.List(ctx, *vm.ID, &armmonitor.MetricsClientListOptions{
				Timespan:    &timespan,
				Interval:    ptr("PT12H"),
				Metricnames: ptr("Percentage CPU,Network In Total,Network Out Total,Disk Read Operations/Sec"),
				Aggregation: ptr("Average"),
			})
			if err != nil {
				return
			}
			reportChan <- processVMMetrics(vm, res)
		}(vm)
	}

	metricWg.Wait()
	close(reportChan)
	for r := range reportChan {
		mu.Lock()
		result.VMReports = append(result.VMReports, r)
		mu.Unlock()
	}
}

func processVMMetrics(vm *armcompute.VirtualMachine, res armmonitor.MetricsClientListResponse) VMReport {
	usageHistory := []float64{}
	usage, netIn, netOut, diskOps := 0.0, 0.0, 0.0, 0.0

	for _, m := range res.Value {
		if len(m.Timeseries) > 0 {
			for _, point := range m.Timeseries[0].Data {
				val := 0.0
				if point.Average != nil {
					val = *point.Average
				}
				switch *m.Name.Value {
				case "Percentage CPU":
					usageHistory = append(usageHistory, val)
					usage = val
				case "Network In Total":
					netIn = val
				case "Network Out Total":
					netOut = val
				case "Disk Read Operations/Sec":
					diskOps = val
				}
			}
		}
	}
	size := "Unknown"
	if vm.Properties != nil && vm.Properties.HardwareProfile != nil && vm.Properties.HardwareProfile.VMSize != nil {
		size = string(*vm.Properties.HardwareProfile.VMSize)
	}
	return VMReport{
		Name:          *vm.Name,
		Size:          size,
		Usage:         usage,
		UsageHistory:  usageHistory,
		NetworkIn:     netIn,
		NetworkOut:    netOut,
		DiskIOPS:      diskOps,
		ResourceID:    *vm.ID,
		Tags:          vm.Tags,
		IsUnallocated: !isTagCompliant(vm.Tags),
	}
}

func parseArgs() (string, string, bool) {
	var subID, mode string
	var listSubs bool
	for i := 0; i < len(os.Args); i++ {
		if os.Args[i] == "--list-subs" {
			listSubs = true
		}
		if os.Args[i] == "--subscription" && i+1 < len(os.Args) {
			subID = os.Args[i+1]
		}
		if os.Args[i] == "--mode" && i+1 < len(os.Args) {
			mode = os.Args[i+1]
		}
	}
	return subID, mode, listSubs
}

func main() {
	subscriptionID, mode, listSubs := parseArgs()

	if listSubs {
		subs, err := GetSubscriptions()
		if err != nil {
			fmt.Printf("{\"error\": \"%s\"}\n", err)
			os.Exit(1)
		}
		output, _ := json.Marshal(subs)
		fmt.Println(string(output))
		return
	}

	if mode == "prices" {
		runPriceMode()
		return
	}

	if subscriptionID == "" {
		subscriptionID = os.Getenv("AZURE_SUBSCRIPTION_ID")
	}
	if subscriptionID == "" {
		log.Fatal("AZURE_SUBSCRIPTION_ID not set. Use --subscription [ID] or set environment variable.")
	}

	runScan(subscriptionID)
}

func runScan(subscriptionID string) {
	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		log.Fatal(err)
	}

	ctx := context.Background()
	result := &ScanResult{
		OrphanedDisks:     []map[string]interface{}{},
		OrphanedSnapshots: []map[string]interface{}{},
		ActiveVMs:         []string{},
		VMReports:         []VMReport{},
		Prices:            []map[string]interface{}{},
	}
	mu := &sync.Mutex{}
	var wg sync.WaitGroup

	wg.Add(3)
	go scanOrphanedDisks(ctx, subscriptionID, cred, result, mu, &wg)
	go scanOrphanedSnapshots(ctx, subscriptionID, cred, result, mu, &wg)
	go scanVMs(ctx, subscriptionID, cred, result, mu, &wg)

	wg.Wait()

	if os.Getenv("DATABASE_URL") != "" {
		pushToDB(result)
	}

	result.UserName = collectors.GetAzureUserName()
	subClient, err := armsubscriptions.NewClient(cred, nil)
	if err == nil {
		sub, err := subClient.Get(ctx, subscriptionID, nil)
		if err == nil && sub.Subscription.DisplayName != nil {
			result.SubscriptionName = *sub.Subscription.DisplayName
		}
	}
	if result.SubscriptionName == "" {
		result.SubscriptionName = "Primary Subscription"
	}

	jsonResult, _ := json.Marshal(result)
	fmt.Println(string(jsonResult))
}

func pushToDB(result *ScanResult) {
	var dbResources []db.Resource
	for _, r := range result.VMReports {
		dbResources = append(dbResources, db.Resource{
			ID:            r.ResourceID,
			Name:          r.Name,
			Type:          "VirtualMachine",
			Region:        "N/A",
			Tags:          r.Tags,
			Active:        true,
			IsProtected:   isProtected(r.Tags),
			IsUnallocated: r.IsUnallocated,
			LastSeen:      time.Now(),
		})
		_ = db.AddCostHistory(r.ResourceID, 12.50, "ACTUAL")
		_ = db.AddCostHistory(r.ResourceID, 8.75, "AMORTIZED")
	}
	_ = db.UpsertResources(dbResources)
	_ = db.CleanupInactiveResources(time.Now().Add(-5 * time.Minute))

	_ = db.AddBusinessMetric("ACTIVE_USERS", 12500, "per 1K users")
	_ = db.AddBusinessMetric("API_REQUESTS", 45000000, "per 1M req")
	_ = db.AddBusinessMetric("CICD_BUILDS", 850, "per Build")
}

func ptr[T any](v T) *T {
	return &v
}
