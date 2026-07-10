package websocket

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// MetricsUpdate represents a real-time metrics update
type MetricsUpdate struct {
	Timestamp time.Time              `json:"timestamp"`
	Metric    string                 `json:"metric"`
	Value     float64                `json:"value"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}

// Client represents a WebSocket client connection
type Client struct {
	ID     string
	conn   *websocket.Conn
	send   chan MetricsUpdate
	hub    *MetricsBroadcaster
	room   string
	mu     sync.Mutex
}

// ClientInfo provides information about a connected client
type ClientInfo struct {
	ID        string    `json:"id"`
	Connected time.Time `json:"connected"`
	Room      string    `json:"room"`
}

// MetricsBroadcaster manages WebSocket client connections and broadcasts metrics updates
type MetricsBroadcaster struct {
	clients    map[*Client]bool
	broadcast  chan MetricsUpdate
	register   chan *Client
	unregister chan *Client
	clientInfo map[string]ClientInfo
	mu         sync.RWMutex
	upgrader   websocket.Upgrader
	running    bool
	stopChan   chan struct{}
}

// NewMetricsBroadcaster creates a new metrics broadcaster
func NewMetricsBroadcaster() *MetricsBroadcaster {
	return &MetricsBroadcaster{
		clients:    make(map[*Client]bool),
		broadcast:  make(chan MetricsUpdate, 256),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		clientInfo: make(map[string]ClientInfo),
		upgrader: websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin: func(r *http.Request) bool {
				// Allow connections from any origin in development
				// In production, implement proper origin checking
				return true
			},
		},
		running:  true,
		stopChan: make(chan struct{}),
	}
}

// Run starts the broadcaster's main loop
func (mb *MetricsBroadcaster) Run() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[MetricsBroadcaster] Panic recovered: %v", r)
		}
	}()

	for {
		select {
		case client := <-mb.register:
			mb.handleRegister(client)
		case client := <-mb.unregister:
			mb.handleUnregister(client)
		case message := <-mb.broadcast:
			mb.handleBroadcast(message)
		case <-mb.stopChan:
			log.Println("[MetricsBroadcaster] Shutting down")
			mb.cleanup()
			return
		}
	}
}

// handleRegister adds a new client to the broadcaster
func (mb *MetricsBroadcaster) handleRegister(client *Client) {
	mb.mu.Lock()
	defer mb.mu.Unlock()

	mb.clients[client] = true
	mb.clientInfo[client.ID] = ClientInfo{
		ID:        client.ID,
		Connected: time.Now(),
		Room:      client.room,
	}

	log.Printf("[MetricsBroadcaster] Client registered: %s (room: %s, total clients: %d)",
		client.ID, client.room, len(mb.clients))
}

// handleUnregister removes a client from the broadcaster
func (mb *MetricsBroadcaster) handleUnregister(client *Client) {
	mb.mu.Lock()
	defer mb.mu.Unlock()

	if _, ok := mb.clients[client]; ok {
		delete(mb.clients, client)
		delete(mb.clientInfo, client.ID)
		// Safely close the channel
		func() {
			defer func() {
				if r := recover(); r != nil {
					log.Printf("[MetricsBroadcaster] Panic recovered while closing client channel: %v", r)
				}
			}()
			close(client.send)
		}()
		log.Printf("[MetricsBroadcaster] Client unregistered: %s (total clients: %d)",
			client.ID, len(mb.clients))
	}
}

// handleBroadcast sends a message to all connected clients
func (mb *MetricsBroadcaster) handleBroadcast(message MetricsUpdate) {
	mb.mu.RLock()
	defer mb.mu.RUnlock()

	for client := range mb.clients {
		select {
		case client.send <- message:
		default:
			// Client send buffer is full, close the connection
			log.Printf("[MetricsBroadcaster] Client %s send buffer full, disconnecting", client.ID)
			mb.unregister <- client
		}
	}
}

// Broadcast sends a metrics update to all connected clients
func (mb *MetricsBroadcaster) Broadcast(metric string, value float64, metadata map[string]interface{}) {
	if !mb.running {
		return
	}

	update := MetricsUpdate{
		Timestamp: time.Now(),
		Metric:    metric,
		Value:     value,
		Metadata:  metadata,
	}

	select {
	case mb.broadcast <- update:
	default:
		log.Printf("[MetricsBroadcaster] Broadcast channel full, message dropped")
	}
}

// BroadcastToRoom sends a metrics update to clients in a specific room
func (mb *MetricsBroadcaster) BroadcastToRoom(room string, metric string, value float64, metadata map[string]interface{}) {
	if !mb.running {
		return
	}

	mb.mu.RLock()
	defer mb.mu.RUnlock()

	update := MetricsUpdate{
		Timestamp: time.Now(),
		Metric:    metric,
		Value:     value,
		Metadata:  metadata,
	}

	for client := range mb.clients {
		if client.room == room {
			select {
			case client.send <- update:
			default:
				log.Printf("[MetricsBroadcaster] Client %s send buffer full, disconnecting", client.ID)
				mb.unregister <- client
			}
		}
	}
}

// HandleWebSocket upgrades an HTTP connection to WebSocket
func (mb *MetricsBroadcaster) HandleWebSocket(w http.ResponseWriter, r *http.Request) {
	if !mb.running {
		http.Error(w, "Broadcaster is not running", http.StatusServiceUnavailable)
		return
	}

	room := r.URL.Query().Get("room")
	clientID := r.URL.Query().Get("client_id")

	if clientID == "" {
		clientID = generateClientID()
	}

	conn, err := mb.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[MetricsBroadcaster] WebSocket upgrade error: %v", err)
		return
	}

	client := &Client{
		ID:   clientID,
		conn: conn,
		send: make(chan MetricsUpdate, 256),
		hub:  mb,
		room: room,
	}

	mb.register <- client

	// Start client goroutines
	go client.writePump()
	go client.readPump()
}

// GetConnectedClients returns information about all connected clients
func (mb *MetricsBroadcaster) GetConnectedClients() []ClientInfo {
	mb.mu.RLock()
	defer mb.mu.RUnlock()

	clients := make([]ClientInfo, 0, len(mb.clientInfo))
	for _, info := range mb.clientInfo {
		clients = append(clients, info)
	}
	return clients
}

// GetClientCount returns the number of connected clients
func (mb *MetricsBroadcaster) GetClientCount() int {
	mb.mu.RLock()
	defer mb.mu.RUnlock()
	return len(mb.clients)
}

// GetClientCountByRoom returns the number of clients in a specific room
func (mb *MetricsBroadcaster) GetClientCountByRoom(room string) int {
	mb.mu.RLock()
	defer mb.mu.RUnlock()

	count := 0
	for client := range mb.clients {
		if client.room == room {
			count++
		}
	}
	return count
}

// writePump handles writing messages to the WebSocket connection
func (c *Client) writePump() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[MetricsBroadcaster] Write panic recovered for client %s: %v", c.ID, r)
		}
		c.conn.Close()
		c.hub.unregister <- c
	}()

	// Set write deadline
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case message, ok := <-c.send:
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			c.mu.Lock()
			err := c.conn.WriteJSON(message)
			c.mu.Unlock()

			if err != nil {
				log.Printf("[MetricsBroadcaster] Write error for client %s: %v", c.ID, err)
				return
			}

		case <-ticker.C:
			// Send ping to keep connection alive
			c.mu.Lock()
			err := c.conn.WriteMessage(websocket.PingMessage, nil)
			c.mu.Unlock()
			if err != nil {
				log.Printf("[MetricsBroadcaster] Ping error for client %s: %v", c.ID, err)
				return
			}
		}
	}
}

// readPump handles reading messages from the WebSocket connection
func (c *Client) readPump() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("[MetricsBroadcaster] Read panic recovered for client %s: %v", c.ID, r)
		}
		c.conn.Close()
		c.hub.unregister <- c
	}()

	// Set read deadline
	c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, _, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("[MetricsBroadcaster] Read error for client %s: %v", c.ID, err)
			}
			break
		}
	}
}

// generateClientID generates a unique client ID
func generateClientID() string {
	timestamp := time.Now().Format("20060102-150405")
	randomBytes := make([]byte, 4)
	if _, err := rand.Read(randomBytes); err != nil {
		log.Printf("[MetricsBroadcaster] Failed to generate random bytes: %v", err)
		// Fallback to timestamp-based ID
		return timestamp + "-" + "fallback"
	}
	return timestamp + "-" + hex.EncodeToString(randomBytes)
}

// Stop gracefully stops the broadcaster
func (mb *MetricsBroadcaster) Stop() {
	mb.mu.Lock()
	if !mb.running {
		mb.mu.Unlock()
		return
	}
	mb.running = false
	mb.mu.Unlock()

	// Signal stop
	close(mb.stopChan)
}

// cleanup closes all client connections
func (mb *MetricsBroadcaster) cleanup() {
	mb.mu.Lock()
	defer mb.mu.Unlock()

	// Close all client connections
	for client := range mb.clients {
		func() {
			defer func() {
				if r := recover(); r != nil {
					log.Printf("[MetricsBroadcaster] Panic recovered while closing client during cleanup: %v", r)
				}
			}()
			close(client.send)
			client.conn.Close()
		}()
		delete(mb.clients, client)
	}

	// Clear all data structures
	mb.clients = make(map[*Client]bool)
	mb.clientInfo = make(map[string]ClientInfo)
}

// RegisterMetricsBroadcasterHandlers registers HTTP handlers for the metrics broadcaster
func RegisterMetricsBroadcasterHandlers(mux *http.ServeMux, broadcaster *MetricsBroadcaster) {
	// WebSocket endpoint
	mux.HandleFunc("/ws/metrics", broadcaster.HandleWebSocket)

	// Client info endpoint
	mux.HandleFunc("/api/ws/clients", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		clients := broadcaster.GetConnectedClients()
		sendJSONResponse(w, map[string]interface{}{
			"clients": clients,
			"count":   len(clients),
		})
	})

	// Broadcast endpoint (for testing)
	mux.HandleFunc("/api/ws/broadcast", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			Metric   string                 `json:"metric"`
			Value    float64                `json:"value"`
			Room     string                 `json:"room,omitempty"`
			Metadata map[string]interface{} `json:"metadata,omitempty"`
		}

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.Room != "" {
			broadcaster.BroadcastToRoom(req.Room, req.Metric, req.Value, req.Metadata)
		} else {
			broadcaster.Broadcast(req.Metric, req.Value, req.Metadata)
		}

		sendJSONResponse(w, map[string]string{"status": "broadcasted"})
	})
}
