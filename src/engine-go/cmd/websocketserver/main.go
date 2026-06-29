package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/websocket"
)

func main() {
	port := flag.Int("port", 7072, "Port for WebSocket batching server")
	flag.Parse()

	// Create a mock emitter for the WebSocket server
	// In a real implementation, this would connect to the actual Socket.IO server
	emitter := websocket.NewMockEmitter()
	websocket.SetEmitter(emitter)

	// Start the WebSocket batcher server
	go func() {
		if err := websocket.StartBatcherServer(*port); err != nil {
			log.Fatalf("Failed to start WebSocket batcher server: %v", err)
		}
	}()

	log.Printf("Go WebSocket Batcher Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down WebSocket batcher server...")
}