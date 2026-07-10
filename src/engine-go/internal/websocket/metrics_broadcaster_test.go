package websocket

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMetricsBroadcaster(t *testing.T) {
	broadcaster := NewMetricsBroadcaster()
	go broadcaster.Run()

	// Wait for broadcaster to start
	time.Sleep(100 * time.Millisecond)

	// Test 1: Broadcast without clients (should not panic)
	broadcaster.Broadcast("test_metric", 123.45, nil)

	// Test 2: Create a test server
	mux := http.NewServeMux()
	RegisterMetricsBroadcasterHandlers(mux, broadcaster)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Test 3: Get connected clients (should be empty)
	resp, err := http.Get(server.URL + "/api/ws/clients")
	if err != nil {
		t.Fatalf("Failed to get clients: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	data, ok := result["data"].(map[string]interface{})
	if !ok {
		t.Fatal("Expected data field in response")
	}

	clients, ok := data["clients"].([]interface{})
	if !ok {
		t.Fatal("Expected clients field in data")
	}

	if len(clients) != 0 {
		t.Errorf("Expected 0 clients, got %d", len(clients))
	}

	// Test 4: Broadcast via HTTP API
	reqBody := `{"metric":"test_metric","value":42.0}`
	resp, err = http.Post(server.URL+"/api/ws/broadcast", "application/json", strings.NewReader(reqBody))
	if err != nil {
		t.Fatalf("Failed to broadcast: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	// Test 5: Get client count
	count := broadcaster.GetClientCount()
	if count != 0 {
		t.Errorf("Expected 0 clients, got %d", count)
	}

	// Test 6: Get client count by room
	roomCount := broadcaster.GetClientCountByRoom("test_room")
	if roomCount != 0 {
		t.Errorf("Expected 0 clients in room, got %d", roomCount)
	}
}

func TestMetricsBroadcasterIntegration(t *testing.T) {
	// This test verifies the integration with the batcher
	broadcaster := NewMetricsBroadcaster()
	go broadcaster.Run()

	batcher := NewWebSocketBatcher(NewMockEmitter(), DefaultBatcherConfig())
	batcher.SetMetricsBroadcaster(broadcaster)

	// Wait for initialization
	time.Sleep(100 * time.Millisecond)

	// Test that metric updates are broadcast
	err := batcher.Emit("metric_update", map[string]interface{}{
		"time":  "2024-01-01T00:00:00Z",
		"value": 123.45,
	}, "test_room")

	if err != nil {
		t.Fatalf("Failed to emit metric: %v", err)
	}

	// Give time for broadcast
	time.Sleep(200 * time.Millisecond)

	// Verify room count (should still be 0 since no actual WebSocket clients)
	roomCount := broadcaster.GetClientCountByRoom("test_room")
	if roomCount != 0 {
		t.Errorf("Expected 0 clients in room, got %d", roomCount)
	}
}
