package collectors

import (
	"context"
	"fmt"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
)

type NetworkUsage struct {
	ResourceID string  `json:"id"`
	NetworkOut float64 `json:"network_out_total"`
}

func GetNetworkMetrics(subscriptionID string, resourceIDs []string) ([]NetworkUsage, error) {
	cred, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		return nil, err
	}

	client, err := armmonitor.NewMetricsClient(subscriptionID, cred, nil)
	if err != nil {
		return nil, err
	}

	var results []NetworkUsage
	endTime := time.Now().UTC()
	startTime := endTime.Add(-24 * time.Hour)
	timespan := fmt.Sprintf("%s/%s", startTime.Format(time.RFC3339), endTime.Format(time.RFC3339))
	metricName := "Network Out Total"
	aggregation := "Total"

	for _, rid := range resourceIDs {
		ctx := context.Background()
		resp, err := client.List(ctx, rid, &armmonitor.MetricsClientListOptions{
			Timespan:    &timespan,
			Metricnames: &metricName,
			Aggregation: &aggregation,
		})
		if err != nil {
			continue
		}

		for _, m := range resp.Value {
			if m.Name != nil && m.Name.Value != nil && *m.Name.Value == metricName {
				for _, ts := range m.Timeseries {
					var total float64
					for _, data := range ts.Data {
						if data.Total != nil {
							total += *data.Total
						}
					}
					results = append(results, NetworkUsage{
						ResourceID: rid,
						NetworkOut: total,
					})
				}
			}
		}
	}

	return results, nil
}
