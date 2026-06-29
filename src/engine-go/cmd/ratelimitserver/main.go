package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/ratelimiter"
)

func main() {
	port := flag.Int("port", 7073, "Port for rate limiting server")
	flag.Parse()

	// Start the rate limiting server
	go func() {
		if err := ratelimiter.StartRateLimiterServer(*port); err != nil {
			log.Fatalf("Failed to start rate limiting server: %v", err)
		}
	}()

	log.Printf("Go Rate Limiter Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down rate limiting server...")
}