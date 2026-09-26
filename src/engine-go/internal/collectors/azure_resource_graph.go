// Package collectors — azure_resource_graph.go
//
// Thin wrapper around the Azure Resource Graph REST API.
// Used by azure_extended_scrapers.go to query arbitrary resource types
// without needing a dedicated ARM client package for each one.

package collectors

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
)

const resourceGraphEndpoint = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2021-03-01"

// azTokenPolicy returns the token request options for the ARM audience.
func azTokenPolicy() policy.TokenRequestOptions {
	return policy.TokenRequestOptions{
		Scopes: []string{"https://management.azure.com/.default"},
	}
}

// azResourceGraphQuery posts a KQL query to the Azure Resource Graph REST API
// and returns the raw response map.
func azResourceGraphQuery(ctx context.Context, bearerToken string, payload map[string]interface{}) (map[string]interface{}, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("resource graph: marshal payload: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, resourceGraphEndpoint, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("resource graph: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+bearerToken)

	httpClient := &http.Client{Timeout: 30 * time.Second}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("resource graph: HTTP request: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("resource graph: read body: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("resource graph: HTTP %d: %s", resp.StatusCode, string(raw))
	}

	var result map[string]interface{}
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, fmt.Errorf("resource graph: unmarshal response: %w", err)
	}

	return result, nil
}
