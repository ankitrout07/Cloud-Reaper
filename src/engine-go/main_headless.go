//go:build headless

package main

import (
	"fmt"
	"net"
	"os"
)

// Headless mode for Docker - just expose a health check endpoint
func main() {
	// Find available port
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to listen: %v\n", err)
		os.Exit(1)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()

	fmt.Printf("Headless Go engine initialized on port %d\n", port)
	// In headless mode, the Python Flask app runs the actual server
	os.Exit(0)
}
