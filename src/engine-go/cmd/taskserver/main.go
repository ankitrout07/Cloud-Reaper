package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"

	"cloud-reaper/engine-go/internal/background"
)

func main() {
	port := flag.Int("port", 7071, "Port for task management server")
	flag.Parse()

	// Start the task server
	go func() {
		if err := background.StartTaskServer(*port); err != nil {
			log.Fatalf("Failed to start task server: %v", err)
		}
	}()

	log.Printf("Go Task Manager Server started on port %d", *port)

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("Shutting down task manager server...")
}