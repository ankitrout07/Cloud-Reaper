// Package bridge — topology.go
//
// Infrastructure Topology Graph API
// ==================================
// GET  /api/v1/topology/graph        → serve topology from DB (no auth required)
// POST /api/v1/topology/scan         → authenticate with Azure, run live scan,
//                                      persist to DB, return fresh topology JSON
//
// Scan credentials
// -----------------
// The POST body can carry Azure service-principal credentials:
//
//	{ "subscription_id": "…",
//	  "tenant_id":       "…",    // optional if env var / az CLI already set
//	  "client_id":       "…",    // optional
//	  "client_secret":  "…" }   // optional
//
// If SP credentials are present they are injected as AZURE_* env-vars for the
// lifetime of the Authenticate() call (protected by topologyScanMu), so that
// DefaultAzureCredential picks them up.  When finished the env-vars are
// restored to their original values.
//
// Image export
// ------------
// Export is entirely client-side: Cytoscape.js cy.png() / cy.jpg() produce
// a Base64 Data URI which is fed to an <a download> link.  No server changes.
//
// CORS
// ----
// Both endpoints set Access-Control-Allow-Origin: * so the browser page (port
// 5001) can fetch from the Go bridge (port 7070).

package bridge

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"sync"

	"cloud-reaper/engine-go/internal/collectors"
	"cloud-reaper/engine-go/internal/db"
	"cloud-reaper/engine-go/internal/models"
)

// topologyScanMu serialises env-var mutations so concurrent scan requests
// don't clobber each other's AZURE_* credentials.
var topologyScanMu sync.Mutex

// ── Cytoscape.js schema ────────────────────────────────────────────────────

// GraphData carries the attributes of a single Cytoscape node or edge.
// Fields are tagged omitempty so one struct covers both element types.
type GraphData struct {
	// Shared fields
	ID    string `json:"id"`
	Label string `json:"label,omitempty"`

	// Node-only fields
	Type   string `json:"type,omitempty"`   // "cloud", "VirtualMachine", "ManagedDisk", …
	Kind   string `json:"kind,omitempty"`   // "node" | "edge"
	Region string `json:"region,omitempty"` // filled from live scan
	SKU    string `json:"sku,omitempty"`    // VM size, disk SKU, …

	// Edge-only fields
	Source string `json:"source,omitempty"`
	Target string `json:"target,omitempty"`
}

// GraphElement is the top-level wrapper Cytoscape.js expects per element.
type GraphElement struct {
	Data GraphData `json:"data"`
}

// topologyResponse is the root envelope returned by both endpoints.
type topologyResponse struct {
	Elements    []GraphElement `json:"elements"`
	NodeCount   int            `json:"node_count"`
	EdgeCount   int            `json:"edge_count"`
	LiveScan    bool           `json:"live_scan"`    // true when data came from a fresh Azure scan
	ResourceCnt int            `json:"resource_cnt"` // raw resource count from scraper
}

// ── Scan request ───────────────────────────────────────────────────────────

// topologyScanRequest is the JSON body for POST /api/v1/topology/scan.
type topologyScanRequest struct {
	SubscriptionID string `json:"subscription_id"`
	TenantID       string `json:"tenant_id,omitempty"`
	ClientID       string `json:"client_id,omitempty"`
	ClientSecret   string `json:"client_secret,omitempty"`
	Provider       string `json:"provider,omitempty"` // defaults to "azure"
}

// ── GET /api/v1/topology/graph ─────────────────────────────────────────────

// handleTopologyGraph serves GET /api/v1/topology/graph.
// Reads the local SQLite DB and returns whatever resources are stored there.
// Falls back to rich mock data when the DB is empty or unreachable.
func handleTopologyGraph(w http.ResponseWriter, r *http.Request) {
	setCORSHeaders(w)
	w.Header().Set("Content-Type", "application/json")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodGet {
		writeTopologyError(w, http.StatusMethodNotAllowed, "GET required")
		return
	}

	elements, err := buildTopologyFromDB()
	if err != nil || len(elements) == 0 {
		fmt.Printf("[topology] DB empty/unavailable (%v) — serving empty topology\n", err)
		elements = []GraphElement{
			{Data: GraphData{ID: "azure_cloud", Label: "Azure Cloud Sub", Type: "cloud", Kind: "node"}},
		}
		writeJSON(w, topologyResponse{
			Elements:  elements,
			NodeCount: 1,
			EdgeCount: 0,
			LiveScan:  false,
		})
		return
	}

	nodeCount, edgeCount := countElements(elements)
	writeJSON(w, topologyResponse{
		Elements:  elements,
		NodeCount: nodeCount,
		EdgeCount: edgeCount,
		LiveScan:  false,
	})
}

// ── POST /api/v1/topology/scan ─────────────────────────────────────────────

// handleTopologyScan authenticates against Azure with the provided credentials,
// runs a live resource scan, persists results to SQLite, and returns the full
// topology JSON in one round trip.
func handleTopologyScan(w http.ResponseWriter, r *http.Request) {
	setCORSHeaders(w)
	w.Header().Set("Content-Type", "application/json")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if r.Method != http.MethodPost {
		writeTopologyError(w, http.StatusMethodNotAllowed, "POST required")
		return
	}

	var req topologyScanRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeTopologyError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	// Fall back to environment if not provided in body.
	if req.SubscriptionID == "" {
		req.SubscriptionID = os.Getenv("AZURE_SUBSCRIPTION_ID")
	}
	if req.Provider == "" {
		req.Provider = "azure"
	}
	if req.SubscriptionID == "" || len(req.SubscriptionID) < 5 {
		writeTopologyError(w, http.StatusBadRequest, "subscription_id is required (at least 5 chars)")
		return
	}

	// ── Optional SP-credential injection ──────────────────────────────────
	// DefaultAzureCredential reads AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET
	// from env at call time.  We temporarily set them if the user supplied them
	// in the request, then restore originals after Authenticate() returns.
	if req.TenantID != "" && req.ClientID != "" && req.ClientSecret != "" {
		topologyScanMu.Lock()
		origTenant := os.Getenv("AZURE_TENANT_ID")
		origClient := os.Getenv("AZURE_CLIENT_ID")
		origSecret := os.Getenv("AZURE_CLIENT_SECRET")

		_ = os.Setenv("AZURE_TENANT_ID", req.TenantID)
		_ = os.Setenv("AZURE_CLIENT_ID", req.ClientID)
		_ = os.Setenv("AZURE_CLIENT_SECRET", req.ClientSecret)

		defer func() {
			_ = os.Setenv("AZURE_TENANT_ID", origTenant)
			_ = os.Setenv("AZURE_CLIENT_ID", origClient)
			_ = os.Setenv("AZURE_CLIENT_SECRET", origSecret)
			topologyScanMu.Unlock()
		}()
	}

	// ── Run live scan ──────────────────────────────────────────────────────
	scraper := &collectors.AzureScraper{}
	if err := scraper.Authenticate(map[string]string{
		"subscription_id": req.SubscriptionID,
	}); err != nil {
		writeTopologyError(w, http.StatusUnauthorized,
			fmt.Sprintf("Azure authentication failed: %v", err))
		return
	}

	resources, err := scraper.ScanResources()
	if err != nil {
		writeTopologyError(w, http.StatusInternalServerError,
			fmt.Sprintf("Resource scan failed: %v", err))
		return
	}

	// ── Persist to SQLite ──────────────────────────────────────────────────
	if _, upsertErr := db.BatchUpsert(resources); upsertErr != nil {
		// Non-fatal: we still build the topology from the in-memory slice.
		fmt.Printf("[topology][warn] BatchUpsert: %v\n", upsertErr)
	}

	// ── Build topology elements ────────────────────────────────────────────
	// Prefer the DB-backed builder (canonical IDs etc.); fall back to the
	// in-memory scraper result if the DB write just failed.
	elements, err := buildTopologyFromDB()
	if err != nil || len(elements) == 0 {
		elements = buildTopologyFromResources(resources, req.SubscriptionID)
	}

	nodeCount, edgeCount := countElements(elements)
	writeJSON(w, topologyResponse{
		Elements:    elements,
		NodeCount:   nodeCount,
		EdgeCount:   edgeCount,
		LiveScan:    true,
		ResourceCnt: len(resources),
	})
}

// ── Graph builders ─────────────────────────────────────────────────────────

// buildTopologyFromDB queries the local SQLite store.
func buildTopologyFromDB() ([]GraphElement, error) {
	database, err := db.Connect()
	if err != nil {
		return nil, fmt.Errorf("connect: %w", err)
	}

	rows, err := database.Query("SELECT id, name, type FROM resources")
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	root := GraphElement{Data: GraphData{
		ID:    "azure_cloud",
		Label: "Azure Cloud Sub",
		Type:  "cloud",
		Kind:  "node",
	}}
	elements := []GraphElement{root}

	edgeIdx := 0
	for rows.Next() {
		var resID, resName, resType string
		if err := rows.Scan(&resID, &resName, &resType); err != nil {
			continue
		}
		label := resName
		if label == "" {
			label = resID
		}
		elements = append(elements,
			GraphElement{Data: GraphData{ID: resID, Label: label, Type: resType, Kind: "node"}},
		)
		edgeIdx++
		elements = append(elements,
			GraphElement{Data: GraphData{
				ID:     fmt.Sprintf("edge-%d", edgeIdx),
				Source: resID,
				Target: "azure_cloud",
				Kind:   "edge",
			}},
		)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows: %w", err)
	}
	if len(elements) == 1 {
		return nil, fmt.Errorf("no resources in DB")
	}
	return elements, nil
}

// buildTopologyFromResources converts a live-scan []models.Resource slice
// directly into Cytoscape elements, bypassing the DB.  Used when the DB
// write fails but we still want to display the scan result.
func buildTopologyFromResources(resources []models.Resource, subscriptionID string) []GraphElement {
	label := "Azure Cloud Sub"
	if subscriptionID != "" {
		label = "Azure — " + subscriptionID[:min(len(subscriptionID), 8)] + "…"
	}

	elements := []GraphElement{
		{Data: GraphData{ID: "azure_cloud", Label: label, Type: "cloud", Kind: "node"}},
	}

	for i, res := range resources {
		name := res.Name
		if name == "" {
			name = res.ID
		}
		elements = append(elements,
			GraphElement{Data: GraphData{
				ID:     res.ID,
				Label:  name,
				Type:   res.Type,
				Kind:   "node",
				Region: res.Region,
				SKU:    res.SKU,
			}},
		)
		elements = append(elements,
			GraphElement{Data: GraphData{
				ID:     fmt.Sprintf("live-edge-%d", i+1),
				Source: res.ID,
				Target: "azure_cloud",
				Kind:   "edge",
			}},
		)
	}
	return elements
}

// ── Mock data removed ────────────────────────────────────────────────────────

// ── Helpers ────────────────────────────────────────────────────────────────

func countElements(elements []GraphElement) (nodes, edges int) {
	for _, el := range elements {
		if el.Data.Source == "" {
			nodes++
		} else {
			edges++
		}
	}
	return
}

func setCORSHeaders(w http.ResponseWriter) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
}

func writeJSON(w http.ResponseWriter, v any) {
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(v)
}

func writeTopologyError(w http.ResponseWriter, code int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
