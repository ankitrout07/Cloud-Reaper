package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/anomaly"
)

func main() {
	port := flag.Int("port", 7076, "Port for anomaly detection server")
	flag.Parse()

	// Start the anomaly detection server
	go func() {
		if err := anomaly.StartAnomalyServer(*port); err != nil {
			log.Fatalf("Failed to start anomaly detection server: %v", err)
		}
	}()

	log.Printf("Go Anomaly Detection Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down anomaly detection server...")
}
