// Package collectors — azure_extended_scrapers.go
//
// Extended Azure Resource Scrapers
// =================================
// Adds concurrent goroutine-based scrapers for resource types that were
// previously blocking the Python GIL in azure_collector.py:
//
//   - Network Security Groups (NSGs)
//   - Public IP Addresses
//   - App Services (Web Apps)
//   - Azure SQL Databases
//   - AKS Managed Clusters
//
// All five scrapers fan out in parallel using a shared errgroup bounded by
// the AzureScraper's existing rate limiter. Each scanner appends to its own
// local slice then the results are merged under a single mutex — zero lock
// contention during the HTTP-bound phase.
//
// Integration
// ------------
// Call (a *AzureScraper) ScanExtendedResources(ctx) to get the full set.
// bridge/server.go should call ScanResources then ScanExtendedResources and
// merge the slices for the complete inventory.
//
// Python side
// ------------
// go_bridge.py: replace azure_collector.py NSG / PublicIP / AppService /
// SQLDatabase / AKS calls with a single POST /scan/extended bridge endpoint
// (defined in bridge/server.go).

package collectors

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/network/armnetwork"

	"cloud-reaper/engine-go/internal/models"
)

// ─── Result aggregator ────────────────────────────────────────────────────────

type extendedScanResult struct {
	resources []models.Resource
	err       error
	name      string
}

// ScanExtendedResources runs five additional Azure resource-type scanners in
// parallel and merges the results. Errors from individual scanners are treated
// as non-fatal — partial results are returned with warnings logged.
func (a *AzureScraper) ScanExtendedResources(ctx context.Context) ([]models.Resource, []string) {
	type scanFn struct {
		name string
		fn   func(ctx context.Context) ([]models.Resource, error)
	}

	scanners := []scanFn{
		{"nsgs", a.scanNSGs},
		{"public_ips", a.scanPublicIPs},
		{"app_services", a.scanAppServices},
		{"sql_databases", a.scanSQLDatabases},
		{"aks_clusters", a.scanAKSClusters},
	}

	resultChan := make(chan extendedScanResult, len(scanners))
	var wg sync.WaitGroup

	for _, s := range scanners {
		wg.Add(1)
		go func(s scanFn) {
			defer wg.Done()
			res, err := s.fn(ctx)
			resultChan <- extendedScanResult{resources: res, err: err, name: s.name}
		}(s)
	}

	go func() {
		wg.Wait()
		close(resultChan)
	}()

	var (
		allResources []models.Resource
		warnings     []string
		mu           sync.Mutex
	)

	for result := range resultChan {
		if result.err != nil {
			mu.Lock()
			warnings = append(warnings, fmt.Sprintf("[azure/%s] scan error (non-fatal): %v", result.name, result.err))
			mu.Unlock()
			continue
		}
		mu.Lock()
		allResources = append(allResources, result.resources...)
		mu.Unlock()
	}

	return allResources, warnings
}

// ─── Network Security Groups ──────────────────────────────────────────────────

func (a *AzureScraper) scanNSGs(ctx context.Context) ([]models.Resource, error) {
	client, err := armnetwork.NewSecurityGroupsClient(a.subscriptionID, a.cred, nil)
	if err != nil {
		return nil, fmt.Errorf("nsg client: %w", err)
	}

	var resources []models.Resource
	pager := client.NewListAllPager(nil)

	for pager.More() {
		_ = a.limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			fmt.Printf("[azure] scan nsgs page error (non-fatal): %v\n", err)
			break
		}

		for _, nsg := range page.Value {
			if nsg == nil || nsg.ID == nil || nsg.Name == nil {
				continue
			}

			tags := azureTagsToMap(nsg.Tags)

			// An NSG is considered orphaned if it has no associated subnets AND
			// no associated network interfaces — it's paying for nothing.
			subnetCount := 0
			nicCount := 0
			if nsg.Properties != nil {
				if nsg.Properties.Subnets != nil {
					subnetCount = len(nsg.Properties.Subnets)
				}
				if nsg.Properties.NetworkInterfaces != nil {
					nicCount = len(nsg.Properties.NetworkInterfaces)
				}
			}
			isOrphaned := subnetCount == 0 && nicCount == 0

			resources = append(resources, models.Resource{
				ID:            *nsg.ID,
				Name:          *nsg.Name,
				Type:          "NetworkSecurityGroup",
				Region:        stringValue(nsg.Location),
				Tags:          tags,
				Active:        true,
				IsProtected:   isAzureProtected(tags),
				IsUnallocated: isOrphaned,
				LastSeen:      time.Now().UTC(),
				Provider:      ProviderAzure,
				SKU:           "nsg",
			})
		}
	}

	return resources, nil
}

// ─── Public IP Addresses ──────────────────────────────────────────────────────

func (a *AzureScraper) scanPublicIPs(ctx context.Context) ([]models.Resource, error) {
	client, err := armnetwork.NewPublicIPAddressesClient(a.subscriptionID, a.cred, nil)
	if err != nil {
		return nil, fmt.Errorf("public ip client: %w", err)
	}

	var resources []models.Resource
	pager := client.NewListAllPager(nil)

	for pager.More() {
		_ = a.limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			fmt.Printf("[azure] scan public ips page error (non-fatal): %v\n", err)
			break
		}

		for _, pip := range page.Value {
			if pip == nil || pip.ID == nil || pip.Name == nil {
				continue
			}

			tags := azureTagsToMap(pip.Tags)

			// A static public IP that is not attached to any resource wastes money.
			isOrphaned := false
			sku := "Dynamic"
			if pip.Properties != nil {
				isOrphaned = pip.Properties.IPConfiguration == nil
				if pip.Properties.PublicIPAllocationMethod != nil {
					sku = string(*pip.Properties.PublicIPAllocationMethod)
				}
			}
			if pip.SKU != nil && pip.SKU.Name != nil {
				sku = string(*pip.SKU.Name)
			}

			resources = append(resources, models.Resource{
				ID:            *pip.ID,
				Name:          *pip.Name,
				Type:          "PublicIPAddress",
				Region:        stringValue(pip.Location),
				Tags:          tags,
				Active:        true,
				IsProtected:   isAzureProtected(tags),
				IsUnallocated: isOrphaned,
				LastSeen:      time.Now().UTC(),
				Provider:      ProviderAzure,
				SKU:           sku,
			})
		}
	}

	return resources, nil
}

// ─── App Services (Web Apps) ──────────────────────────────────────────────────
// Uses the Azure Resource Manager REST API via armnetwork-style approach.
// We use a raw ARM REST call via the Azure SDK armcore client to avoid pulling
// in the full armappservice module (not yet in go.sum).

func (a *AzureScraper) scanAppServices(ctx context.Context) ([]models.Resource, error) {
	// Use Resource Graph via armnetwork's underlying credential to query
	// Microsoft.Web/sites resources without needing the full armwebsite package.
	// We perform a simple REST call using the existing credential.

	resources, err := a.queryResourceGraphType(ctx, "Microsoft.Web/sites", "AppService")
	if err != nil {
		return nil, fmt.Errorf("app services scan: %w", err)
	}
	return resources, nil
}

// ─── Azure SQL Databases ──────────────────────────────────────────────────────

func (a *AzureScraper) scanSQLDatabases(ctx context.Context) ([]models.Resource, error) {
	resources, err := a.queryResourceGraphType(ctx, "Microsoft.Sql/servers/databases", "SQLDatabase")
	if err != nil {
		return nil, fmt.Errorf("sql databases scan: %w", err)
	}
	return resources, nil
}

// ─── AKS Managed Clusters ─────────────────────────────────────────────────────

func (a *AzureScraper) scanAKSClusters(ctx context.Context) ([]models.Resource, error) {
	resources, err := a.queryResourceGraphType(ctx, "Microsoft.ContainerService/managedClusters", "AKSCluster")
	if err != nil {
		return nil, fmt.Errorf("aks clusters scan: %w", err)
	}
	return resources, nil
}

// ─── Resource Graph helper ───────────────────────────────────────────────────
//
// queryResourceGraphType calls the Azure Resource Graph REST API to list
// resources of a given type. This avoids importing a separate ARM package for
// every resource type and stays within the already-loaded azidentity credential.
//
// Response shape (simplified):
//
//	{
//	  "data": {
//	    "columns": [...],
//	    "rows":    [[id, name, location, tags, sku, powerState], ...]
//	  }
//	}

func (a *AzureScraper) queryResourceGraphType(ctx context.Context, resourceType, reaperType string) ([]models.Resource, error) {
	_ = a.limiter.Wait(ctx)

	// Get a bearer token from the existing DefaultAzureCredential
	token, err := a.cred.GetToken(ctx, azTokenPolicy())
	if err != nil {
		return nil, fmt.Errorf("get token: %w", err)
	}

	// Build the KQL query
	query := fmt.Sprintf(
		`Resources | where type =~ '%s' | project id, name, location, tags, sku, properties`,
		strings.ToLower(resourceType),
	)

	payload := map[string]interface{}{
		"subscriptions": []string{a.subscriptionID},
		"query":         query,
		"options": map[string]interface{}{
			"$top": 1000,
		},
	}

	resp, err := azResourceGraphQuery(ctx, token.Token, payload)
	if err != nil {
		return nil, err
	}

	return parseResourceGraphResponse(resp, reaperType), nil
}

// parseResourceGraphResponse converts the generic Resource Graph row format into
// the unified models.Resource structure.
func parseResourceGraphResponse(resp map[string]interface{}, resourceType string) []models.Resource {
	now := time.Now().UTC()
	var resources []models.Resource

	data, ok := resp["data"].(map[string]interface{})
	if !ok {
		return resources
	}

	rows, ok := data["rows"].([]interface{})
	if !ok {
		return resources
	}

	columns, _ := data["columns"].([]interface{})
	colIndex := buildColumnIndex(columns)

	for _, rawRow := range rows {
		row, ok := rawRow.([]interface{})
		if !ok || len(row) == 0 {
			continue
		}

		id := safeString(row, colIndex["id"])
		name := safeString(row, colIndex["name"])
		location := safeString(row, colIndex["location"])
		if id == "" || name == "" {
			continue
		}

		tags := extractTags(row, colIndex["tags"])
		sku := extractSKU(row, colIndex["sku"])
		isIdle := extractIdleSignal(row, colIndex["properties"])

		resources = append(resources, models.Resource{
			ID:            id,
			Name:          name,
			Type:          resourceType,
			Region:        location,
			Tags:          tags,
			Active:        true,
			IsProtected:   isAzureProtected(tags),
			IsUnallocated: isIdle,
			LastSeen:      now,
			Provider:      ProviderAzure,
			SKU:           sku,
		})
	}

	return resources
}

// ─── Resource Graph HTTP helpers ─────────────────────────────────────────────

func buildColumnIndex(columns []interface{}) map[string]int {
	idx := make(map[string]int, len(columns))
	for i, col := range columns {
		if m, ok := col.(map[string]interface{}); ok {
			if name, ok := m["name"].(string); ok {
				idx[strings.ToLower(name)] = i
			}
		}
	}
	return idx
}

func safeString(row []interface{}, idx int) string {
	if idx < 0 || idx >= len(row) {
		return ""
	}
	if s, ok := row[idx].(string); ok {
		return s
	}
	return ""
}

func extractTags(row []interface{}, idx int) map[string]string {
	if idx < 0 || idx >= len(row) {
		return map[string]string{}
	}
	m, ok := row[idx].(map[string]interface{})
	if !ok {
		return map[string]string{}
	}
	out := make(map[string]string, len(m))
	for k, v := range m {
		if s, ok := v.(string); ok {
			out[k] = s
		}
	}
	return out
}

func extractSKU(row []interface{}, idx int) string {
	if idx < 0 || idx >= len(row) {
		return "unknown"
	}
	switch v := row[idx].(type) {
	case string:
		return v
	case map[string]interface{}:
		if name, ok := v["name"].(string); ok {
			return name
		}
	}
	return "unknown"
}

// extractIdleSignal checks the properties blob for power-state or capacity
// signals that suggest the resource is stopped/idle.
func extractIdleSignal(row []interface{}, idx int) bool {
	if idx < 0 || idx >= len(row) {
		return false
	}
	props, ok := row[idx].(map[string]interface{})
	if !ok {
		return false
	}
	// App Services: state == "Stopped"
	if state, ok := props["state"].(string); ok && strings.EqualFold(state, "Stopped") {
		return true
	}
	// AKS: powerState.code == "Stopped"
	if ps, ok := props["powerState"].(map[string]interface{}); ok {
		if code, ok := ps["code"].(string); ok && strings.EqualFold(code, "Stopped") {
			return true
		}
	}
	return false
}
