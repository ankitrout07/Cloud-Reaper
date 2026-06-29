package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/calculator"
)

func main() {
	port := flag.Int("port", 7075, "Port for cost calculator server")
	flag.Parse()

	// Start the calculator server
	go func() {
		if err := calculator.StartCalculatorServer(*port); err != nil {
			log.Fatalf("Failed to start calculator server: %v", err)
		}
	}()

	log.Printf("Go Cost Calculator Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down cost calculator server...")
}