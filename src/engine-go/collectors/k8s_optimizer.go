package collectors

import (
	"encoding/json"
	"fmt"
)

type K8sNodeMetrics struct {
	NodeName      string             `json:"node_name"`
	CPUAllocated  float64            `json:"cpu_allocated"`
	MemAllocated  float64            `json:"mem_allocated"`
	Capacity      map[string]float64 `json:"capacity"`
	PodsScheduled int                `json:"pods_count"`
}

type ConsolidationPlan struct {
	Action          string  `json:"action"`
	TargetNode      string  `json:"target_node"`
	Reason          string  `json:"reason"`
	PotentialSaving float64 `json:"potential_saving"`
}

// MostAllocatedOptimizer implements the bin-packing strategy for K8s nodes
func MostAllocatedOptimizer(nodes []K8sNodeMetrics) []ConsolidationPlan {
	var plans []ConsolidationPlan

	for _, node := range nodes {
		cpuUtil := node.CPUAllocated / node.Capacity["cpu"]
		// MostAllocated logic: If density is below 20%, suggest moving pods
		if cpuUtil < 0.20 && node.PodsScheduled > 0 {
			plans = append(plans, ConsolidationPlan{
				Action:          "DRAIN",
				TargetNode:      node.NodeName,
				Reason:          fmt.Sprintf("Underutilized density (%.1f%%). Consolidation required.", cpuUtil*100),
				PotentialSaving: 40.0, // Average cost of a Standard_D2s_v3 node in USD/mo
			})
		}
	}

	return plans
}

// ExportMapping returns a JSON string for the Python engine
func ExportMapping(v interface{}) string {
	b, _ := json.Marshal(v)
	return string(b)
}
