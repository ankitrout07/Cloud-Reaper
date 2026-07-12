package collectors

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/aws/aws-sdk-go-v2/service/ec2/types"
	"golang.org/x/oauth2/google"
	"golang.org/x/time/rate"
	"google.golang.org/api/compute/v1"
	"google.golang.org/api/option"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"

	"cloud-reaper/engine-go/internal/models"
)

// AWSScraper implements CloudProvider for AWS accounts.
type AWSScraper struct {
	creds  map[string]string
	region string
	client *ec2.Client
}

func (s *AWSScraper) Authenticate(creds map[string]string) error {
	s.creds = creds
	accessKey := firstNonEmpty(creds, "access_key_id", "AWS_ACCESS_KEY_ID")
	secretKey := firstNonEmpty(creds, "secret_access_key", "AWS_SECRET_ACCESS_KEY")
	if accessKey == "" || secretKey == "" {
		return fmt.Errorf("aws: access_key_id and secret_access_key are required")
	}

	s.region = firstNonEmpty(creds, "region", "AWS_REGION")
	if s.region == "" {
		s.region = "us-east-1"
	}

	cfg, err := config.LoadDefaultConfig(context.Background(),
		config.WithRegion(s.region),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(accessKey, secretKey, "")),
	)
	if err != nil {
		return fmt.Errorf("aws: authenticate: %w", err)
	}
	s.client = ec2.NewFromConfig(cfg)
	return nil
}

func (s *AWSScraper) ScanResources() ([]models.Resource, error) {
	if s.client == nil {
		return nil, fmt.Errorf("aws: not authenticated")
	}

	ctx := context.Background()
	var resources []models.Resource
	now := time.Now().UTC()

	instPager := ec2.NewDescribeInstancesPaginator(s.client, &ec2.DescribeInstancesInput{})
	for instPager.HasMorePages() {
		page, err := instPager.NextPage(ctx)
		if err != nil {
			return nil, fmt.Errorf("aws: describe instances: %w", err)
		}
		for _, reservation := range page.Reservations {
			for _, inst := range reservation.Instances {
				if inst.InstanceId == nil {
					continue
				}
				tags := awsTagsToMap(inst.Tags)
				name := *inst.InstanceId
				if v, ok := tags["Name"]; ok {
					name = v
				}
				sku := string(inst.InstanceType)
				state := string(inst.State.Name)
				resources = append(resources, models.Resource{
					ID:            *inst.InstanceId,
					Name:          name,
					Type:          "EC2Instance",
					Region:        s.region,
					Tags:          tags,
					Active:        state == string(types.InstanceStateNameRunning),
					IsProtected:   isAWSProtected(tags),
					IsUnallocated: state == string(types.InstanceStateNameStopped),
					LastSeen:      now,
					Provider:      ProviderAWS,
					SKU:           sku,
				})
			}
		}
	}

	volPager := ec2.NewDescribeVolumesPaginator(s.client, &ec2.DescribeVolumesInput{
		Filters: []types.Filter{{
			Name:   aws.String("status"),
			Values: []string{"available"},
		}},
	})
	for volPager.HasMorePages() {
		page, err := volPager.NextPage(ctx)
		if err != nil {
			return resources, fmt.Errorf("aws: describe volumes: %w", err)
		}
		for _, vol := range page.Volumes {
			if vol.VolumeId == nil {
				continue
			}
			tags := awsTagsToMap(vol.Tags)
			resources = append(resources, models.Resource{
				ID:            *vol.VolumeId,
				Name:          *vol.VolumeId,
				Type:          "OrphanedEBSVolume",
				Region:        s.region,
				Tags:          tags,
				Active:        true,
				IsProtected:   isAWSProtected(tags),
				IsUnallocated: true,
				LastSeen:      now,
				Provider:      ProviderAWS,
				SKU:           string(vol.VolumeType),
			})
		}
	}

	snapPager := ec2.NewDescribeSnapshotsPaginator(s.client, &ec2.DescribeSnapshotsInput{
		OwnerIds: []string{"self"},
	})
	for snapPager.HasMorePages() {
		page, err := snapPager.NextPage(ctx)
		if err != nil {
			break // Non-fatal; skip snapshots on error
		}
		for _, snap := range page.Snapshots {
			if snap.StartTime != nil && time.Since(*snap.StartTime) > 30*24*time.Hour {
				tags := awsTagsToMap(snap.Tags)
				resources = append(resources, models.Resource{
					ID:            *snap.SnapshotId,
					Name:          *snap.SnapshotId,
					Type:          "OrphanedEBSSnapshot",
					Region:        s.region,
					Tags:          tags,
					Active:        true,
					IsProtected:   isAWSProtected(tags),
					IsUnallocated: true,
					LastSeen:      now,
					Provider:      ProviderAWS,
					SKU:           "snapshot",
				})
			}
		}
	}

	return resources, nil
}

func (s *AWSScraper) GetHourlyRate(sku string) (float64, error) {
	price, err := FetchAWSPrice(sku, s.region)
	if err == nil && price > 0 {
		return price, nil
	}

	rates := map[string]float64{
		"t3.micro":  0.0104,
		"t3.small":  0.0208,
		"m5.large":  0.096,
		"m5.xlarge": 0.192,
		"gp3":       0.00008,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0.05, nil
}

func awsTagsToMap(tags []types.Tag) map[string]string {
	out := make(map[string]string, len(tags))
	for _, t := range tags {
		if t.Key != nil && t.Value != nil {
			out[*t.Key] = *t.Value
		}
	}
	return out
}

func isAWSProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
			return true
		}
	}
	return false
}

func firstNonEmpty(m map[string]string, keys ...string) string {
	for _, k := range keys {
		if v := strings.TrimSpace(m[k]); v != "" {
			return v
		}
	}
	return ""
}

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
	var resources []models.Resource

	vms, err := a.scanVMs(ctx)
	if err != nil {
		return nil, err
	}
	resources = append(resources, vms...)

	disks, err := a.scanDisks(ctx)
	if err == nil {
		resources = append(resources, disks...)
	}

	return resources, nil
}

func (a *AzureScraper) scanVMs(ctx context.Context) ([]models.Resource, error) {
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

	// semaphore limits concurrent Azure Monitor API calls to avoid 429s
	const maxConcurrent = 10
	sem := make(chan struct{}, maxConcurrent)

	for pager.More() {
		_ = a.limiter.Wait(ctx)
		page, err := pager.NextPage(ctx)
		if err != nil {
			break
		}

		// Fan out CPU usage fetches in parallel using goroutines
		type vmResult struct {
			vm    *armcompute.VirtualMachine
			usage float64
		}

		resultChan := make(chan vmResult, len(page.Value))
		var wg sync.WaitGroup

		for _, vm := range page.Value {
			if vm == nil || vm.ID == nil || vm.Name == nil {
				continue
			}

			wg.Add(1)
			go func(vm *armcompute.VirtualMachine) {
				defer wg.Done()
				sem <- struct{}{}        // acquire slot
				defer func() { <-sem }() // release slot
				usage := a.latestCPUPercent(ctx, monitorClient, *vm.ID)
				resultChan <- vmResult{vm: vm, usage: usage}
			}(vm)
		}

		// Wait for all goroutines to complete
		go func() {
			wg.Wait()
			close(resultChan)
		}()

		// Collect results
		for result := range resultChan {
			vm := result.vm
			usage := result.usage

			tags := azureTagsToMap(vm.Tags)
			
			edges := []string{}
			if vm.Properties != nil {
				if vm.Properties.StorageProfile != nil {
					if vm.Properties.StorageProfile.OSDisk != nil && vm.Properties.StorageProfile.OSDisk.ManagedDisk != nil && vm.Properties.StorageProfile.OSDisk.ManagedDisk.ID != nil {
						edges = append(edges, *vm.Properties.StorageProfile.OSDisk.ManagedDisk.ID)
					}
					for _, disk := range vm.Properties.StorageProfile.DataDisks {
						if disk != nil && disk.ManagedDisk != nil && disk.ManagedDisk.ID != nil {
							edges = append(edges, *disk.ManagedDisk.ID)
						}
					}
				}
				if vm.Properties.NetworkProfile != nil && vm.Properties.NetworkProfile.NetworkInterfaces != nil {
					for _, nic := range vm.Properties.NetworkProfile.NetworkInterfaces {
						if nic != nil && nic.ID != nil {
							edges = append(edges, *nic.ID)
						}
					}
				}
			}
			if len(edges) > 0 {
				tags["_reaper_edges"] = strings.Join(edges, ",")
			}

			sku := "Unknown"
			if vm.Properties != nil && vm.Properties.HardwareProfile != nil && vm.Properties.HardwareProfile.VMSize != nil {
				sku = string(*vm.Properties.HardwareProfile.VMSize)
			}
			region := vmLocation(vm)

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
				Provider:      ProviderAzure,
				SKU:           sku,
				Usage:         usage,
			})
		}
	}
	return resources, nil
}

func (a *AzureScraper) scanDisks(ctx context.Context) ([]models.Resource, error) {
	diskClient, err := armcompute.NewDisksClient(a.subscriptionID, a.cred, nil)
	if err != nil {
		return nil, err
	}

	var resources []models.Resource
	diskPager := diskClient.NewListPager(nil)
	for diskPager.More() {
		_ = a.limiter.Wait(ctx)
		page, err := diskPager.NextPage(ctx)
		if err != nil {
			break
		}
		for _, disk := range page.Value {
			if disk == nil || disk.ID == nil || disk.Name == nil {
				continue
			}
			
			isOrphaned := disk.ManagedBy == nil
			diskType := "ManagedDisk"
			if isOrphaned {
				diskType = "OrphanedDisk"
			}
			
			tags := azureTagsToMap(disk.Tags)
			resources = append(resources, models.Resource{
				ID:            *disk.ID,
				Name:          *disk.Name,
				Type:          diskType,
				Region:        stringValue(disk.Location),
				Tags:          tags,
				Active:        true,
				IsProtected:   isAzureProtected(tags),
				IsUnallocated: isOrphaned,
				LastSeen:      time.Now().UTC(),
				Provider:      ProviderAzure,
				SKU:           diskSKU(disk),
			})
		}
	}
	return resources, nil
}

func (a *AzureScraper) GetHourlyRate(sku string) (float64, error) {
	price, err := FetchAzurePrice(sku, "")
	if err == nil && price > 0 {
		return price, nil
	}

	rates := map[string]float64{
		"Standard_D2s_v3": 0.096,
		"Standard_D4s_v3": 0.192,
		"Standard_E4s_v3": 0.252,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0.1, nil
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
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
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
	return Unknown
}

func diskSKU(disk *armcompute.Disk) string {
	if disk.SKU != nil && disk.SKU.Name != nil {
		return string(*disk.SKU.Name)
	}
	return Unknown
}

func stringValue(s *string) string {
	if s == nil {
		return Unknown
	}
	return *s
}

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

	insts, err := s.scanInstances(ctx, now)
	if err != nil {
		return nil, err
	}
	resources = append(resources, insts...)

	disks, err := s.scanDisks(now)
	if err != nil {
		return resources, err
	}
	resources = append(resources, disks...)

	snaps, err := s.scanSnapshots(now)
	if err != nil {
		return resources, err
	}
	resources = append(resources, snaps...)

	return resources, nil
}

func (s *GCPScraper) scanInstances(ctx context.Context, now time.Time) ([]models.Resource, error) {
	var resources []models.Resource
	req := s.service.Instances.AggregatedList(s.projectID)
	err := req.Pages(ctx, func(page *compute.InstanceAggregatedList) error {
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
					Provider:      ProviderGCP,
					SKU:           sku,
				})
			}
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("gcp: list instances: %w", err)
	}
	return resources, nil
}

func (s *GCPScraper) scanDisks(now time.Time) ([]models.Resource, error) {
	var resources []models.Resource
	disks, err := s.service.Disks.AggregatedList(s.projectID).Do()
	if err != nil {
		return nil, fmt.Errorf("gcp: list disks: %w", err)
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
				Provider:      ProviderGCP,
				SKU:           disk.Type,
			})
		}
	}
	return resources, nil
}

func (s *GCPScraper) scanSnapshots(now time.Time) ([]models.Resource, error) {
	var resources []models.Resource
	snapshots, err := s.service.Snapshots.List(s.projectID).Do()
	if err != nil {
		return nil, fmt.Errorf("gcp: list snapshots: %w", err)
	}
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
				Provider:      ProviderGCP,
				SKU:           "snapshot",
			})
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

// K8sScraper implements CloudProvider for Kubernetes clusters (nodes as billable units).
type K8sScraper struct {
	creds     map[string]string
	clientset kubernetes.Interface
}

func (s *K8sScraper) Authenticate(creds map[string]string) error {
	s.creds = creds
	kubeconfig := firstNonEmpty(creds, "kubeconfig", "KUBECONFIG")
	contextName := creds["context"]

	var cfg *rest.Config
	var err error

	switch {
	case kubeconfig != "":
		var path string
		path, err = expandHome(kubeconfig)
		if err != nil {
			return fmt.Errorf("k8s: kubeconfig path: %w", err)
		}
		loading := clientcmd.NewDefaultClientConfigLoadingRules()
		loading.ExplicitPath = path
		overrides := &clientcmd.ConfigOverrides{}
		if contextName != "" {
			overrides.CurrentContext = contextName
		}
		cfg, err = clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loading, overrides).ClientConfig()
	default:
		cfg, err = rest.InClusterConfig()
	}
	if err != nil {
		return fmt.Errorf("k8s: authenticate: %w", err)
	}

	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return fmt.Errorf("k8s: build client: %w", err)
	}
	s.clientset = cs
	return nil
}

func (s *K8sScraper) ScanResources() ([]models.Resource, error) {
	if s.clientset == nil {
		return nil, fmt.Errorf("k8s: not authenticated")
	}

	ctx := context.Background()
	nodes, err := s.clientset.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("k8s: list nodes: %w", err)
	}

	now := time.Now().UTC()
	var resources []models.Resource
	for _, node := range nodes.Items {
		resources = append(resources, nodeToResource(node, now))
	}

	pods, err := s.clientset.CoreV1().Pods("").List(ctx, metav1.ListOptions{
		FieldSelector: "status.phase=Failed",
	})
	if err == nil {
		for _, pod := range pods.Items {
			if pod.DeletionTimestamp != nil {
				continue
			}
			resources = append(resources, models.Resource{
				ID:            string(pod.UID),
				Name:          fmt.Sprintf("%s/%s", pod.Namespace, pod.Name),
				Type:          "FailedPod",
				Region:        "cluster",
				Tags:          podLabelsToMap(pod.Labels),
				Active:        true,
				IsProtected:   false,
				IsUnallocated: true,
				LastSeen:      now,
				Provider:      ProviderK8s,
				SKU:           "pod",
			})
		}
	}

	return resources, nil
}

func (s *K8sScraper) GetHourlyRate(sku string) (float64, error) {
	rates := map[string]float64{
		"node":            0.05,
		"pod":             0.001,
		"Standard_D2s_v3": 0.096,
	}
	if rate, ok := rates[sku]; ok {
		return rate, nil
	}
	return 0, fmt.Errorf("k8s: hourly rate not found for sku %q", sku)
}

func nodeToResource(node corev1.Node, seen time.Time) models.Resource {
	tags := podLabelsToMap(node.Labels)
	instanceType := node.Labels["node.kubernetes.io/instance-type"]
	if instanceType == "" {
		instanceType = node.Labels["beta.kubernetes.io/instance-type"]
	}
	if instanceType == "" {
		instanceType = "node"
	}

	cpuCap := node.Status.Capacity.Cpu().AsApproximateFloat64()
	cpuAlloc := node.Status.Allocatable.Cpu().AsApproximateFloat64()
	util := 0.0
	if cpuCap > 0 {
		util = cpuAlloc / cpuCap
	}

	return models.Resource{
		ID:            string(node.UID),
		Name:          node.Name,
		Type:          "KubernetesNode",
		Region:        "cluster",
		Tags:          tags,
		Active:        isNodeReady(node),
		IsProtected:   isK8sProtected(tags),
		IsUnallocated: util < 0.20,
		LastSeen:      seen,
		Provider:      ProviderK8s,
		SKU:           instanceType,
	}
}

func isNodeReady(node corev1.Node) bool {
	for _, c := range node.Status.Conditions {
		if c.Type == corev1.NodeReady {
			return c.Status == corev1.ConditionTrue
		}
	}
	return false
}

func isK8sProtected(tags map[string]string) bool {
	for k, v := range tags {
		key := strings.ToLower(k)
		val := strings.ToLower(v)
		if (key == KeyReaperIgnore && val == ValueTrue) || (key == KeyEnvironment && val == ValueProduction) {
			return true
		}
	}
	return false
}

func podLabelsToMap(labels map[string]string) map[string]string {
	if labels == nil {
		return map[string]string{}
	}
	out := make(map[string]string, len(labels))
	for k, v := range labels {
		out[k] = v
	}
	return out
}

func expandHome(path string) (string, error) {
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		return filepath.Join(home, path[2:]), nil
	}
	return path, nil
}
