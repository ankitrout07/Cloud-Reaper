package main

import (
	"flag"
	"log"

	"cloud-reaper/engine-go/internal/websocket"
)

func main() {
	port := flag.Int("port", 7072, "Port for WebSocket batching server")
	flag.Parse()

	// Create a mock emitter for the WebSocket server
	// In a real implementation, this would connect to the actual Socket.IO server
	emitter := websocket.NewMockEmitter()
	websocket.SetEmitter(emitter)

	log.Printf("Starting Go WebSocket Batcher Server on port %d", *port)

	// Start the WebSocket batcher server (includes graceful shutdown)
	if err := websocket.StartBatcherServer(*port); err != nil {
		log.Fatalf("Failed to start WebSocket batcher server: %v", err)
	}
}
