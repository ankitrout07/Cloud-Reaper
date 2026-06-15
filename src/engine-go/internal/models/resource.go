package models

import "time"

// Resource is the unified inventory shape returned by every CloudProvider scraper.
type Resource struct {
	ID            string
	Name          string
	Type          string
	Region        string
	Tags          map[string]string
	Active        bool
	IsProtected   bool
	IsUnallocated bool
	LastSeen      time.Time
	Provider      string // azure, aws, gcp, k8s
	SKU           string // instance type / VM size / node pool SKU
}
