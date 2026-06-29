package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/rag"
)

func main() {
	port := flag.Int("port", 7074, "Port for RAG search server")
	flag.Parse()

	// Start the RAG server
	go func() {
		if err := rag.StartRAGServer(*port); err != nil {
			log.Fatalf("Failed to start RAG server: %v", err)
		}
	}()

	log.Printf("Go RAG Search Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down RAG search server...")
}
