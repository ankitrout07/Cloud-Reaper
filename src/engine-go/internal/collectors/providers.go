package collectors

import (
	"cloud-reaper/engine-go/internal/models"
	"fmt"
	"strings"
)

const (
	KeyReaperIgnore = "reaper-ignore"
	ValueTrue       = "true"
	KeyEnvironment  = "environment"
	ValueProduction = "production"
	Unknown         = "unknown"

	ProviderAzure = "azure"
	ProviderAWS   = "aws"
	ProviderGCP   = "gcp"
	ProviderK8s   = "k8s"
)

// CloudProvider is the contract every cloud scraper must implement.
// It allows the engine to use a standardized interface across Azure, AWS,
// GCP, and Kubernetes.
type CloudProvider interface {
	Authenticate(creds map[string]string) error
	ScanResources() ([]models.Resource, error)
	GetHourlyRate(sku string) (float64, error)
}

// NewProvider returns a CloudProvider implementation for the requested
// cloud provider type.
func NewProvider(providerType string) (CloudProvider, error) {
	switch strings.ToLower(strings.TrimSpace(providerType)) {
	case ProviderAzure:
		return &AzureScraper{}, nil
	case ProviderAWS:
		return &AWSScraper{}, nil
	case ProviderGCP:
		return &GCPScraper{}, nil
	case ProviderK8s, "kubernetes":
		return &K8sScraper{}, nil
	default:
		return nil, fmt.Errorf("unsupported provider type: %q", providerType)
	}
}
