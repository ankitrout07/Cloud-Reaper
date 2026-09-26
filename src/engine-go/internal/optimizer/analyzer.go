// Package optimizer — analyzer.go
//
// Go Cost Optimizer
// ==================
// Implements the resource analysis logic previously in Python's
// cost_optimizer.py. All analysis functions run in parallel per-resource
// using goroutines + errgroup, replacing the serial Python for-loops that
// were GIL-bound and couldn't exceed max_workers parallelism.
//
// Supported resource types
// -------------------------
//   Compute  : "VirtualMachine", "EC2Instance", "GCEInstance"
//   Storage  : "OrphanedDisk", "OrphanedEBSVolume", "ManagedDisk", "disk"
//   Database : "SQLDatabase", "database", "db"
//   Network  : "PublicIPAddress", "NetworkSecurityGroup", "loadbalancer"
//
// Bridge integration
// -------------------
// Expose via POST /api/v1/optimizer/analyze on the bridge server (server.go).
// Python calls this endpoint and replaces the 6 _analyze_*_resource methods
// with a single awaited HTTP request.

package optimizer

import (
	"fmt"
	"math"
	"strings"
	"sync"
	"time"
)

// ─── Domain types ─────────────────────────────────────────────────────────────

// OptimizationCategory mirrors cost_optimizer.py OptimizationCategory.
type OptimizationCategory string

const (
	CategoryCompute      OptimizationCategory = "compute"
	CategoryStorage      OptimizationCategory = "storage"
	CategoryNetwork      OptimizationCategory = "network"
	CategoryDatabase     OptimizationCategory = "database"
	CategoryArchitecture OptimizationCategory = "architecture"
)

// Priority mirrors cost_optimizer.py Priority.
type Priority string

const (
	PriorityCritical Priority = "critical"
	PriorityHigh     Priority = "high"
	PriorityMedium   Priority = "medium"
	PriorityLow      Priority = "low"
)

// RiskLevel mirrors cost_optimizer.py RiskLevel.
type RiskLevel string

const (
	RiskSafe   RiskLevel = "safe"
	RiskLow    RiskLevel = "low"
	RiskMedium RiskLevel = "medium"
	RiskHigh   RiskLevel = "high"
)

// ResourceMetrics carries utilisation signals for a single resource.
type ResourceMetrics struct {
	CPUUtilization        float64 `json:"cpu_utilization"`
	MemoryUtilization     float64 `json:"memory_utilization"`
	DiskUtilization       float64 `json:"disk_utilization"`
	NetworkInMbps         float64 `json:"network_in_mbps"`
	NetworkOutMbps        float64 `json:"network_out_mbps"`
	IOPS                  float64 `json:"iops"`
	LatencyMs             float64 `json:"latency_ms"`
	ErrorRate             float64 `json:"error_rate"`
	UptimePercentage      float64 `json:"uptime_percentage"`
	PeakCPUUtilization    float64 `json:"peak_cpu_utilization"`
	PeakMemoryUtilization float64 `json:"peak_memory_utilization"`
}

// ResourceData is the input descriptor for a single cloud resource.
type ResourceData struct {
	ID       string            `json:"id"`
	Name     string            `json:"name"`
	Type     string            `json:"type"`     // e.g. "VirtualMachine"
	Provider string            `json:"provider"` // azure, aws, gcp
	SKU      string            `json:"sku"`
	Region   string            `json:"region"`
	Tags     map[string]string `json:"tags"`
}

// Recommendation mirrors cost_optimizer.py CostRecommendation.
type Recommendation struct {
	ID                        string               `json:"id"`
	Title                     string               `json:"title"`
	Description               string               `json:"description"`
	Category                  OptimizationCategory `json:"category"`
	Priority                  Priority             `json:"priority"`
	RiskLevel                 RiskLevel            `json:"risk_level"`
	EstimatedMonthlySavings   float64              `json:"estimated_monthly_savings"`
	EstimatedSavingsPct       float64              `json:"estimated_savings_percentage"`
	ImplementationEffort      string               `json:"implementation_effort"`
	ResourceID                string               `json:"resource_id"`
	ResourceName              string               `json:"resource_name"`
	ResourceType              string               `json:"resource_type"`
	CurrentCost               float64              `json:"current_cost"`
	RecommendedAction         string               `json:"recommended_action"`
	RecommendedConfig         map[string]any       `json:"recommended_config"`
	ImplementationSteps       []string             `json:"implementation_steps"`
	PotentialIssues           []string             `json:"potential_issues"`
	CreatedAt                 string               `json:"created_at"`
}

// AnalyzeRequest is the POST body for /api/v1/optimizer/analyze.
type AnalyzeRequest struct {
	Resources []struct {
		Resource    ResourceData    `json:"resource"`
		Metrics     ResourceMetrics `json:"metrics"`
		CurrentCost float64         `json:"current_cost"`
	} `json:"resources"`
}

// AnalyzeResponse is the JSON response from the optimizer.
type AnalyzeResponse struct {
	Recommendations []Recommendation `json:"recommendations"`
	TotalSavings    float64          `json:"total_potential_savings"`
	ResourceCount   int              `json:"resource_count"`
	AnalyzedAt      string           `json:"analyzed_at"`
}

// ─── Optimizer ────────────────────────────────────────────────────────────────

// Optimizer is the main entry point.  It is stateless and safe for concurrent
// use.
type Optimizer struct{}

// NewOptimizer returns a new Optimizer instance.
func NewOptimizer() *Optimizer { return &Optimizer{} }

// AnalyzeAll runs AnalyzeResource for every item in the request concurrently
// using a goroutine fan-out bounded by a semaphore to avoid creating O(N) OS
// threads for very large subscriptions.
func (o *Optimizer) AnalyzeAll(req AnalyzeRequest) AnalyzeResponse {
	const maxConcurrent = 32

	type result struct {
		recs []Recommendation
	}

	items := req.Resources
	resultCh := make(chan result, len(items))
	sem := make(chan struct{}, maxConcurrent)

	var wg sync.WaitGroup
	for _, item := range items {
		wg.Add(1)
		go func(r ResourceData, m ResourceMetrics, cost float64) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			recs := o.AnalyzeResource(r, m, cost)
			resultCh <- result{recs: recs}
		}(item.Resource, item.Metrics, item.CurrentCost)
	}

	go func() {
		wg.Wait()
		close(resultCh)
	}()

	var (
		allRecs      []Recommendation
		totalSavings float64
	)
	for res := range resultCh {
		allRecs = append(allRecs, res.recs...)
		for _, rec := range res.recs {
			totalSavings += rec.EstimatedMonthlySavings
		}
	}

	return AnalyzeResponse{
		Recommendations: allRecs,
		TotalSavings:    math.Round(totalSavings*100) / 100,
		ResourceCount:   len(items),
		AnalyzedAt:      time.Now().UTC().Format(time.RFC3339),
	}
}

// AnalyzeResource dispatches to the correct type-specific analyzer and always
// appends a regional-arbitrage check at the end.
func (o *Optimizer) AnalyzeResource(r ResourceData, m ResourceMetrics, cost float64) []Recommendation {
	t := strings.ToLower(r.Type)

	var recs []Recommendation
	switch {
	case isComputeType(t):
		recs = append(recs, o.analyzeCompute(r, m, cost)...)
	case isStorageType(t):
		recs = append(recs, o.analyzeStorage(r, m, cost)...)
	case isDatabaseType(t):
		recs = append(recs, o.analyzeDatabase(r, m, cost)...)
	case isNetworkType(t):
		recs = append(recs, o.analyzeNetwork(r, m, cost)...)
	}
	// Regional arbitrage applies to all resource types.
	if arb := o.analyzeRegionalArbitrage(r, m, cost); arb != nil {
		recs = append(recs, *arb)
	}
	return recs
}

func isComputeType(t string) bool {
	return strings.Contains(t, "vm") || strings.Contains(t, "virtualmachine") ||
		strings.Contains(t, "instance") || strings.Contains(t, "compute")
}

func isStorageType(t string) bool {
	return strings.Contains(t, "disk") || strings.Contains(t, "storage") ||
		strings.Contains(t, "volume") || strings.Contains(t, "snapshot")
}

func isDatabaseType(t string) bool {
	return strings.Contains(t, "database") || strings.Contains(t, "sql") ||
		strings.Contains(t, "db")
}

func isNetworkType(t string) bool {
	return strings.Contains(t, "network") || strings.Contains(t, "publicip") ||
		strings.Contains(t, "loadbalancer") || strings.Contains(t, "lb")
}

// ─── Compute analysis ─────────────────────────────────────────────────────────

func (o *Optimizer) analyzeCompute(r ResourceData, m ResourceMetrics, cost float64) []Recommendation {
	var recs []Recommendation

	if rec := o.rightsizingRec(r, m, cost); rec != nil {
		recs = append(recs, *rec)
	}
	if rec := o.idleComputeRec(r, m, cost); rec != nil {
		recs = append(recs, *rec)
	}
	if rec := o.reservedInstanceRec(r, m, cost); rec != nil {
		recs = append(recs, *rec)
	}
	if rec := o.spotInstanceRec(r, m, cost); rec != nil {
		recs = append(recs, *rec)
	}
	if rec := o.architectureRec(r, m, cost); rec != nil {
		recs = append(recs, *rec)
	}

	return recs
}

func (o *Optimizer) rightsizingRec(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	var savingsPct float64
	var priority Priority
	var title, desc string

	switch {
	case m.CPUUtilization < 30 && m.MemoryUtilization < 50:
		// Significantly over-provisioned
		savingsPct = 0.60
		priority = PriorityHigh
		title = fmt.Sprintf("Right-size %s — Significant Cost Reduction", r.Name)
		desc = fmt.Sprintf("Resource is significantly over-provisioned (%.1f%% CPU, %.1f%% Memory). Downsizing can save ~60%%.", m.CPUUtilization, m.MemoryUtilization)

	case m.CPUUtilization < 50 && m.MemoryUtilization < 70:
		// Moderately over-provisioned
		savingsPct = 0.35
		priority = PriorityMedium
		title = fmt.Sprintf("Right-size %s — Moderate Cost Reduction", r.Name)
		desc = fmt.Sprintf("Resource is moderately over-provisioned (%.1f%% CPU, %.1f%% Memory). Downsizing can save ~35%%.", m.CPUUtilization, m.MemoryUtilization)

	case m.PeakCPUUtilization < 40 && m.PeakMemoryUtilization < 60:
		// Consistently low even at peak
		savingsPct = 0.25
		priority = PriorityMedium
		title = fmt.Sprintf("Right-size %s — Consistently Underutilised", r.Name)
		desc = fmt.Sprintf("Resource is underutilised even at peak (%.1f%% peak CPU). Conservative downsize can save ~25%%.", m.PeakCPUUtilization)

	default:
		return nil
	}

	return &Recommendation{
		ID:                      fmt.Sprintf("rightsize_%s", r.ID),
		Title:                   title,
		Description:             desc,
		Category:                CategoryCompute,
		Priority:                priority,
		RiskLevel:               RiskLow,
		EstimatedMonthlySavings: math.Round(cost*savingsPct*100) / 100,
		EstimatedSavingsPct:     savingsPct,
		ImplementationEffort:    "low",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "resize_vm",
		RecommendedConfig:       map[string]any{"current_sku": r.SKU},
		ImplementationSteps: []string{
			"1. Snapshot the VM disk for rollback.",
			"2. Deallocate the VM.",
			"3. Resize to the recommended SKU.",
			"4. Start the VM and verify application health.",
		},
		PotentialIssues: []string{"Brief downtime during resize (< 2 min)."},
		CreatedAt:       time.Now().UTC().Format(time.RFC3339),
	}
}

func (o *Optimizer) idleComputeRec(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	if m.CPUUtilization >= 5 || m.UptimePercentage < 10 {
		return nil
	}
	return &Recommendation{
		ID:                      fmt.Sprintf("idle_%s", r.ID),
		Title:                   fmt.Sprintf("Idle resource: %s — Deallocate or Delete", r.Name),
		Description:             fmt.Sprintf("%.1f%% CPU over the measurement period suggests this resource is idle. Deallocating or removing it eliminates 100%% of compute cost.", m.CPUUtilization),
		Category:                CategoryCompute,
		Priority:                PriorityCritical,
		RiskLevel:               RiskMedium,
		EstimatedMonthlySavings: cost,
		EstimatedSavingsPct:     1.0,
		ImplementationEffort:    "low",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "deallocate_or_delete",
		RecommendedConfig:       map[string]any{},
		ImplementationSteps: []string{
			"1. Confirm no active users or services depend on this resource.",
			"2. Deallocate (or delete) via the cloud console or CLI.",
		},
		PotentialIssues: []string{"Verify no cron jobs or batch workloads scheduled on this VM."},
		CreatedAt:       time.Now().UTC().Format(time.RFC3339),
	}
}

func (o *Optimizer) reservedInstanceRec(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	// Only recommend RIs for consistently high-utilisation VMs (> 60% CPU).
	if m.CPUUtilization < 60 || cost < 50 {
		return nil
	}
	saving := cost * 0.40
	return &Recommendation{
		ID:                      fmt.Sprintf("ri_%s", r.ID),
		Title:                   fmt.Sprintf("Reserved Instance for %s — 40%% Savings", r.Name),
		Description:             "This VM has consistently high utilisation. A 1-year reserved instance commitment typically saves 40% versus on-demand pricing.",
		Category:                CategoryCompute,
		Priority:                PriorityHigh,
		RiskLevel:               RiskSafe,
		EstimatedMonthlySavings: math.Round(saving*100) / 100,
		EstimatedSavingsPct:     0.40,
		ImplementationEffort:    "low",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "purchase_reserved_instance",
		RecommendedConfig:       map[string]any{"commitment_term": "1_year", "sku": r.SKU},
		ImplementationSteps:     []string{"Purchase a Reserved Instance (RI) matching the current SKU and region."},
		PotentialIssues:         []string{"RI cannot be easily refunded once purchased."},
		CreatedAt:               time.Now().UTC().Format(time.RFC3339),
	}
}

func (o *Optimizer) spotInstanceRec(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	// Spot only makes sense for fault-tolerant, stateless workloads.
	if m.UptimePercentage > 99 || cost < 20 {
		return nil
	}
	saving := cost * 0.70
	return &Recommendation{
		ID:                      fmt.Sprintf("spot_%s", r.ID),
		Title:                   fmt.Sprintf("Spot/Preemptible Instance for %s — Up to 70%% Savings", r.Name),
		Description:             "This VM's uptime pattern suggests it may be suitable for a spot/preemptible instance, saving up to 70%% versus on-demand.",
		Category:                CategoryCompute,
		Priority:                PriorityMedium,
		RiskLevel:               RiskMedium,
		EstimatedMonthlySavings: math.Round(saving*100) / 100,
		EstimatedSavingsPct:     0.70,
		ImplementationEffort:    "medium",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "migrate_to_spot",
		RecommendedConfig:       map[string]any{"eviction_policy": "Deallocate"},
		ImplementationSteps:     []string{"Ensure the workload handles preemption gracefully.", "Switch the VM to spot pricing via the cloud console."},
		PotentialIssues:         []string{"Spot VMs can be evicted with 30-second notice."},
		CreatedAt:               time.Now().UTC().Format(time.RFC3339),
	}
}

func (o *Optimizer) architectureRec(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	// Recommend serverless migration only for very-low, bursty utilisation.
	if m.CPUUtilization > 20 || cost < 30 {
		return nil
	}
	saving := cost * 0.50
	return &Recommendation{
		ID:                      fmt.Sprintf("serverless_%s", r.ID),
		Title:                   fmt.Sprintf("Migrate %s to Serverless/Container", r.Name),
		Description:             "Very low average utilisation suggests this workload could run on a serverless or containerised platform at a fraction of the cost.",
		Category:                CategoryArchitecture,
		Priority:                PriorityMedium,
		RiskLevel:               RiskHigh,
		EstimatedMonthlySavings: math.Round(saving*100) / 100,
		EstimatedSavingsPct:     0.50,
		ImplementationEffort:    "high",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "migrate_to_serverless",
		RecommendedConfig:       map[string]any{},
		ImplementationSteps:     []string{"Containerize the workload.", "Deploy to Azure Container Apps / AWS Lambda / Cloud Run."},
		PotentialIssues:         []string{"Significant re-architecture effort may be required."},
		CreatedAt:               time.Now().UTC().Format(time.RFC3339),
	}
}

// ─── Storage analysis ─────────────────────────────────────────────────────────

func (o *Optimizer) analyzeStorage(r ResourceData, m ResourceMetrics, cost float64) []Recommendation {
	var recs []Recommendation

	// Orphaned disk — no VM attached
	if strings.Contains(strings.ToLower(r.Type), "orphan") {
		recs = append(recs, Recommendation{
			ID:                      fmt.Sprintf("orphan_disk_%s", r.ID),
			Title:                   fmt.Sprintf("Orphaned Disk: %s — Delete or Archive", r.Name),
			Description:             "This disk is not attached to any VM. Deleting or snapshotting it eliminates 100% of its storage cost.",
			Category:                CategoryStorage,
			Priority:                PriorityHigh,
			RiskLevel:               RiskLow,
			EstimatedMonthlySavings: cost,
			EstimatedSavingsPct:     1.0,
			ImplementationEffort:    "low",
			ResourceID:              r.ID,
			ResourceName:            r.Name,
			ResourceType:            r.Type,
			CurrentCost:             cost,
			RecommendedAction:       "delete_orphaned_disk",
			RecommendedConfig:       map[string]any{},
			ImplementationSteps:     []string{"Verify the disk is not needed, then delete it."},
			PotentialIssues:         []string{"Deletion is irreversible — snapshot first if unsure."},
			CreatedAt:               time.Now().UTC().Format(time.RFC3339),
		})
	}

	// Low-disk utilisation — consider tier downgrade
	if m.DiskUtilization > 0 && m.DiskUtilization < 30 && cost > 20 {
		recs = append(recs, Recommendation{
			ID:                      fmt.Sprintf("storage_tier_%s", r.ID),
			Title:                   fmt.Sprintf("Downgrade Storage Tier for %s", r.Name),
			Description:             fmt.Sprintf("Disk utilisation is %.1f%%. Switching to a lower-performance tier (e.g. Standard HDD) can save ~40%%.", m.DiskUtilization),
			Category:                CategoryStorage,
			Priority:                PriorityMedium,
			RiskLevel:               RiskLow,
			EstimatedMonthlySavings: math.Round(cost*0.40*100) / 100,
			EstimatedSavingsPct:     0.40,
			ImplementationEffort:    "low",
			ResourceID:              r.ID,
			ResourceName:            r.Name,
			ResourceType:            r.Type,
			CurrentCost:             cost,
			RecommendedAction:       "downgrade_storage_tier",
			RecommendedConfig:       map[string]any{"target_tier": "Standard_LRS"},
			ImplementationSteps:     []string{"Change the disk SKU to Standard HDD via the portal or CLI."},
			PotentialIssues:         []string{"IOPS and throughput will be reduced."},
			CreatedAt:               time.Now().UTC().Format(time.RFC3339),
		})
	}

	return recs
}

// ─── Database analysis ────────────────────────────────────────────────────────

func (o *Optimizer) analyzeDatabase(r ResourceData, m ResourceMetrics, cost float64) []Recommendation {
	var recs []Recommendation

	if m.CPUUtilization < 20 && m.MemoryUtilization < 40 && cost > 50 {
		recs = append(recs, Recommendation{
			ID:                      fmt.Sprintf("db_rightsize_%s", r.ID),
			Title:                   fmt.Sprintf("Right-size Database %s", r.Name),
			Description:             fmt.Sprintf("Database is under-utilised (%.1f%% CPU). Scaling down compute tier or switching to serverless mode can save 30-50%%.", m.CPUUtilization),
			Category:                CategoryDatabase,
			Priority:                PriorityHigh,
			RiskLevel:               RiskMedium,
			EstimatedMonthlySavings: math.Round(cost*0.40*100) / 100,
			EstimatedSavingsPct:     0.40,
			ImplementationEffort:    "medium",
			ResourceID:              r.ID,
			ResourceName:            r.Name,
			ResourceType:            r.Type,
			CurrentCost:             cost,
			RecommendedAction:       "resize_database",
			RecommendedConfig:       map[string]any{"consider": "serverless_tier"},
			ImplementationSteps:     []string{"Scale down the database vCores in the portal.", "Consider switching to serverless auto-pause."},
			PotentialIssues:         []string{"Requires a brief maintenance window."},
			CreatedAt:               time.Now().UTC().Format(time.RFC3339),
		})
	}

	return recs
}

// ─── Network analysis ─────────────────────────────────────────────────────────

func (o *Optimizer) analyzeNetwork(r ResourceData, m ResourceMetrics, cost float64) []Recommendation {
	var recs []Recommendation

	// Unattached public IPs
	if strings.Contains(strings.ToLower(r.Type), "publicip") && cost > 0 {
		recs = append(recs, Recommendation{
			ID:                      fmt.Sprintf("unattached_pip_%s", r.ID),
			Title:                   fmt.Sprintf("Unattached Public IP: %s", r.Name),
			Description:             "This static public IP is not associated with any resource. Releasing it eliminates its reserved-IP fee.",
			Category:                CategoryNetwork,
			Priority:                PriorityHigh,
			RiskLevel:               RiskSafe,
			EstimatedMonthlySavings: cost,
			EstimatedSavingsPct:     1.0,
			ImplementationEffort:    "low",
			ResourceID:              r.ID,
			ResourceName:            r.Name,
			ResourceType:            r.Type,
			CurrentCost:             cost,
			RecommendedAction:       "release_public_ip",
			RecommendedConfig:       map[string]any{},
			ImplementationSteps:     []string{"Confirm the IP is not used, then release/delete it."},
			PotentialIssues:         []string{"Releasing a static IP is irreversible — you will not get the same address back."},
			CreatedAt:               time.Now().UTC().Format(time.RFC3339),
		})
	}

	// Low-traffic load balancer
	if strings.Contains(strings.ToLower(r.Type), "loadbalancer") && m.NetworkInMbps < 1.0 && cost > 30 {
		recs = append(recs, Recommendation{
			ID:                      fmt.Sprintf("idle_lb_%s", r.ID),
			Title:                   fmt.Sprintf("Idle Load Balancer: %s", r.Name),
			Description:             fmt.Sprintf("Load balancer is handling %.2f Mbps inbound — very low. Consider removing it or consolidating with another LB.", m.NetworkInMbps),
			Category:                CategoryNetwork,
			Priority:                PriorityMedium,
			RiskLevel:               RiskMedium,
			EstimatedMonthlySavings: cost,
			EstimatedSavingsPct:     1.0,
			ImplementationEffort:    "medium",
			ResourceID:              r.ID,
			ResourceName:            r.Name,
			ResourceType:            r.Type,
			CurrentCost:             cost,
			RecommendedAction:       "remove_or_consolidate_lb",
			RecommendedConfig:       map[string]any{},
			ImplementationSteps:     []string{"Audit backend pools.", "Redirect traffic and delete the load balancer."},
			PotentialIssues:         []string{"Traffic routing changes require testing."},
			CreatedAt:               time.Now().UTC().Format(time.RFC3339),
		})
	}

	return recs
}

// ─── Regional arbitrage ───────────────────────────────────────────────────────

// arbitrageRegions contains cheaper alternative regions for common expensive ones.
var arbitrageRegions = map[string]struct {
	cheaper string
	savings float64
}{
	"westeurope":   {"northeurope", 0.12},
	"eastus":       {"eastus2", 0.08},
	"westus":       {"westus2", 0.10},
	"australiaeast": {"australiasoutheast", 0.10},
	"japaneast":    {"japanwest", 0.08},
}

func (o *Optimizer) analyzeRegionalArbitrage(r ResourceData, m ResourceMetrics, cost float64) *Recommendation {
	region := strings.ToLower(r.Region)
	alt, ok := arbitrageRegions[region]
	if !ok || cost < 50 {
		return nil
	}
	saving := cost * alt.savings
	return &Recommendation{
		ID:                      fmt.Sprintf("arb_%s", r.ID),
		Title:                   fmt.Sprintf("Regional Arbitrage for %s", r.Name),
		Description:             fmt.Sprintf("Migrating from %s to %s could save ~%.0f%% on this resource's cost.", r.Region, alt.cheaper, alt.savings*100),
		Category:                CategoryCompute,
		Priority:                PriorityLow,
		RiskLevel:               RiskHigh,
		EstimatedMonthlySavings: math.Round(saving*100) / 100,
		EstimatedSavingsPct:     alt.savings,
		ImplementationEffort:    "high",
		ResourceID:              r.ID,
		ResourceName:            r.Name,
		ResourceType:            r.Type,
		CurrentCost:             cost,
		RecommendedAction:       "migrate_region",
		RecommendedConfig:       map[string]any{"target_region": alt.cheaper},
		ImplementationSteps:     []string{"Validate data residency requirements.", "Plan a full migration to the cheaper region."},
		PotentialIssues:         []string{"Data sovereignty and latency constraints may prohibit this move."},
		CreatedAt:               time.Now().UTC().Format(time.RFC3339),
	}
}
