package collectors

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"golang.org/x/oauth2/google"
	"google.golang.org/api/compute/v1"
	"google.golang.org/api/option"

	"cloud-reaper/engine-go/models"
)

// GCPScraper implements CloudProvider for Google Cloud projects.
type GCPScraper struct {
	creds     map[string]string
	projectID string
	service   *compute.Service
}

func (s *GCPScraper) Authenticate(creds map[string]string) error {
	s.creds = creds
	s.projectID = firstNonEmpty(creds, "project_id", "GCP_PROJECT_ID")
	if s.projectID == "" {
		return fmt.Errorf("gcp: project_id is required")
	}

	saJSON := firstNonEmpty(creds, "service_account_json", "GCP_SERVICE_ACCOUNT_JSON")
	if saJSON == "" {
		return fmt.Errorf("gcp: service_account_json is required")
	}

	ctx := context.Background()
	var opts []option.ClientOption
	if _, err := os.Stat(saJSON); err == nil {
		opts = append(opts, option.WithCredentialsFile(saJSON))
	} else {
		if !json.Valid([]byte(saJSON)) {
			return fmt.Errorf("gcp: service_account_json must be a file path or valid JSON")
		}
		jwtCfg, err := google.JWTConfigFromJSON([]byte(saJSON), compute.CloudPlatformScope)
		if err != nil {
			return fmt.Errorf("gcp: parse service account: %w", err)
		}
		opts = append(opts, option.WithTokenSource(jwtCfg.TokenSource(ctx)))
	}

	svc, err := compute.NewService(ctx, opts...)
	if err != nil {
		return fmt.Errorf("gcp: authenticate: %w", err)
	}
	s.service = svc
	return nil
}

func (s *GCPScraper) ScanResources() ([]models.Resource, error) {
	if s.service == nil {
		return nil, fmt.Errorf("gcp: not authenticated")
	}

	ctx := context.Background()
	var resources []models.Resource
	now := time.Now().UTC()

	req := s.service.Instances.AggregatedList(s.projectID)
	if err := req.Pages(ctx, func(page *compute.InstanceAggregatedList) error {
		for zone, scoped := range page.Items {
			region := gcpZoneToRegion(zone)
			for _, inst := range scoped.Instances {
				if inst == nil {
					continue
				}
				tags := inst.Labels
				if tags == nil {
					tags = map[string]string{}
				}
				name := inst.Name
				if name == "" {
					name = fmt.Sprintf("%d", inst.Id)
				}
				sku := inst.MachineType
				if parts := strings.Split(sku, "/"); len(parts) > 0 {
					sku = parts[len(parts)-1]
				}
				resources = append(resources, models.Resource{
					ID:            fmt.Sprintf("gcp://%s/%s", s.projectID, inst.SelfLink),
					Name:          name,
					Type:          "GCEInstance",
					Region:        region,
					Tags:          tags,
					Active:        inst.Status == "RUNNING",
					IsProtected:   isGCPProtected(tags),
					IsUnallocated: inst.Status == "TERMINATED",
					LastSeen:      now,
					Provider:      "gcp",
					SKU:           sku,
				})
			}
		}
		return nil
	}); err != nil {
		return nil, fmt.Errorf("gcp: list instances: %w", err)
	}

	disks, err := s.service.Disks.AggregatedList(s.projectID).Do()
	if err != nil {
		return resources, fmt.Errorf("gcp: list disks: %w", err)
	}
	for zone, scoped := range disks.Items {
		region := gcpZoneToRegion(zone)
		for _, disk := range scoped.Disks {
			if len(disk.Users) > 0 {
				continue
			}
			tags := disk.Labels
			if tags == nil {
				tags = map[string]string{}
			}
			resources = append(resources, models.Resource{
				ID:            disk.SelfLink,
				Name:          disk.Name,
				Type:          "OrphanedPersistentDisk",
				Region:        region,
				Tags:          tags,
				Active:        true,
				IsProtected:   isGCPProtected(tags),
				IsUnallocated: true,
				LastSeen:      now,
				Provider:      "gcp",
				SKU:           disk.Type,
			})
		}
	}

	snapshots, err := s.service.Snapshots.List(s.projectID).Do()
	if err == nil {
		for _, snap := range snapshots.Items {
			createTime, _ := time.Parse(time.RFC3339, snap.CreationTimestamp)
			if !createTime.IsZero() && time.Since(createTime) > 30*24*time.Hour {
				tags := snap.Labels
				if tags == nil {
					tags = map[string]string{}
				}
				resources = append(resources, models.Resource{
					ID:            snap.SelfLink,
					Name:          snap.Name,
					Type:          "OrphanedGCPSnapshot",
					Region:        "global",
					Tags:          tags,
					Active:        true,
					IsProtected:   isGCPProtected(tags),
					IsUnallocated: true,
					LastSeen:      now,
					Provider:      "gcp",
					SKU:           "snapshot",
				})
			}
		}
	}

	return resources, nil
}


func (s *GCPScraper) GetHourlyRate(sku string) (float64, error) {
	rates := map[string]float64{
		"n1-standard-1": 0.0475,
		"n1-standard-2": 0.0950,
		"e2-medium":     0.0335,
		"pd-standard":   0.000054,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0, fmt.Errorf("gcp: hourly rate not found for sku %q", sku)
}

func gcpZoneToRegion(zoneKey string) string {
	// zoneKey is like "zones/us-central1-a"
	parts := strings.Split(zoneKey, "/")
	if len(parts) < 2 {
		return zoneKey
	}
	zone := parts[len(parts)-1]
	if i := strings.LastIndex(zone, "-"); i > 0 {
		return zone[:i]
	}
	return zone
}

func isGCPProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
			return true
		}
	}
	return false
}
