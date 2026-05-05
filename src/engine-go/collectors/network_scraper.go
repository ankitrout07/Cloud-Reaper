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
		pager := client.NewListPager(rid, &armmonitor.MetricsClientListOptions{
			Timespan:        &timespan,
			Interval:        nil,
			Metricnames:     &metricName,
			Aggregation:     &aggregation,
			Top:             nil,
			Orderby:         nil,
			Filter:          nil,
			ResultType:      nil,
			Metricnamespace: nil,
		})

		for pager.More() {
			page, err := pager.NextPage(context.Background())
			if err != nil {
				break
			}
			for _, m := range page.Value {
				if m.Name != nil && *m.Name.Value == metricName {
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
	}

	return results, nil
}
