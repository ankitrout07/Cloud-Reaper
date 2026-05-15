package collectors

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
	"golang.org/x/time/rate"

	"cloud-reaper/engine-go/models"
)

// AzureScraper implements CloudProvider for Azure subscriptions.
type AzureScraper struct {
	creds          map[string]string
	subscriptionID string
	cred           *azidentity.DefaultAzureCredential
	limiter        *rate.Limiter
}

func (a *AzureScraper) Authenticate(creds map[string]string) error {
	a.creds = creds
	a.subscriptionID = creds["subscription_id"]
	if a.subscriptionID == "" {
		a.subscriptionID = creds["AZURE_SUBSCRIPTION_ID"]
	}
	if a.subscriptionID == "" {
		return fmt.Errorf("azure: subscription_id is required")
	}

	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		return fmt.Errorf("azure: authenticate: %w", err)
	}
	a.cred = cred
	a.limiter = rate.NewLimiter(rate.Every(time.Second/10), 10)
	return nil
}

func (a *AzureScraper) ScanResources() ([]models.Resource, error) {
	if a.cred == nil {
		return nil, fmt.Errorf("azure: not authenticated")
	}

	ctx := context.Background()
	vmClient, err := armcompute.NewVirtualMachinesClient(a.subscriptionID, a.cred, nil)
	if err != nil {
		return nil, err
	}
	monitorClient, err := armmonitor.NewMetricsClient(a.subscriptionID, a.cred, nil)
	if err != nil {
		return nil, err
	}

	var resources []models.Resource
	pager := vmClient.NewListAllPager(nil)
	for pager.More() {
		_ = a.limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			break
		}
		for _, vm := range page.Value {
			if vm == nil || vm.ID == nil || vm.Name == nil {
				continue
			}
			tags := azureTagsToMap(vm.Tags)
			sku := "Unknown"
			if vm.Properties != nil && vm.Properties.HardwareProfile != nil && vm.Properties.HardwareProfile.VMSize != nil {
				sku = string(*vm.Properties.HardwareProfile.VMSize)
			}
			region := vmLocation(vm)
			usage := a.latestCPUPercent(ctx, monitorClient, *vm.ID)

			resources = append(resources, models.Resource{
				ID:            *vm.ID,
				Name:          *vm.Name,
				Type:          "VirtualMachine",
				Region:        region,
				Tags:          tags,
				Active:        true,
				IsProtected:   isAzureProtected(tags),
				IsUnallocated: !isAzureTagCompliant(tags) || usage < 5.0,
				LastSeen:      time.Now().UTC(),
				Provider:      "azure",
				SKU:           sku,
			})
		}
	}

	diskClient, err := armcompute.NewDisksClient(a.subscriptionID, a.cred, nil)
	if err == nil {
		diskPager := diskClient.NewListPager(nil)
		for diskPager.More() {
			_ = a.limiter.Wait(ctx)
			page, err := diskPager.NextPage(ctx)
			if err != nil {
				break
			}
			for _, disk := range page.Value {
				if disk == nil || disk.ManagedBy != nil || disk.ID == nil || disk.Name == nil {
					continue
				}
				tags := azureTagsToMap(disk.Tags)
				resources = append(resources, models.Resource{
					ID:            *disk.ID,
					Name:          *disk.Name,
					Type:          "OrphanedDisk",
					Region:        stringValue(disk.Location),
					Tags:          tags,
					Active:        true,
					IsProtected:   isAzureProtected(tags),
					IsUnallocated: true,
					LastSeen:      time.Now().UTC(),
					Provider:      "azure",
					SKU:           diskSKU(disk),
				})
			}
		}
	}

	return resources, nil
}

func (a *AzureScraper) GetHourlyRate(sku string) (float64, error) {
	rates := map[string]float64{
		"Standard_D2s_v3": 0.096,
		"Standard_D4s_v3": 0.192,
		"Standard_E4s_v3": 0.252,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0, fmt.Errorf("azure: hourly rate not found for sku %q", sku)
}

func (a *AzureScraper) latestCPUPercent(ctx context.Context, client *armmonitor.MetricsClient, resourceID string) float64 {
	end := time.Now().UTC()
	start := end.Add(-24 * time.Hour)
	timespan := fmt.Sprintf("%s/%s", start.Format(time.RFC3339), end.Format(time.RFC3339))
	interval := "PT1H"
	metric := "Percentage CPU"
	agg := "Average"

	_ = a.limiter.Wait(ctx)
	resp, err := client.List(ctx, resourceID, &armmonitor.MetricsClientListOptions{
		Timespan:    &timespan,
		Interval:    &interval,
		Metricnames: &metric,
		Aggregation: &agg,
	})
	if err != nil {
		return 0
	}
	for _, m := range resp.Value {
		for _, ts := range m.Timeseries {
			for _, pt := range ts.Data {
				if pt.Average != nil {
					return *pt.Average
				}
			}
		}
	}
	return 0
}

func azureTagsToMap(tags map[string]*string) map[string]string {
	out := make(map[string]string, len(tags))
	for k, v := range tags {
		if v != nil {
			out[k] = *v
		}
	}
	return out
}

func isAzureProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == "reaper-ignore" && val == "true") || (key == "environment" && val == "production") {
			return true
		}
	}
	return false
}

func isAzureTagCompliant(tags map[string]string) bool {
	required := []string{"owner", "project"}
	for _, req := range required {
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

func vmLocation(vm *armcompute.VirtualMachine) string {
	if vm.Location != nil {
		return *vm.Location
	}
	return "unknown"
}

func diskSKU(disk *armcompute.Disk) string {
	if disk.SKU != nil && disk.SKU.Name != nil {
		return string(*disk.SKU.Name)
	}
	return "unknown"
}

func stringValue(s *string) string {
	if s == nil {
		return "unknown"
	}
	return *s
}
