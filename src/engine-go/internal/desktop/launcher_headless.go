//go:build headless

package desktop

import (
	"fmt"
)

// Stub implementation for headless mode (Docker)
func Run() {
	fmt.Println("Running in headless mode - desktop launcher disabled")
	fmt.Println("Use the web interface at http://localhost:5001")
	// Keep process alive briefly then exit - the Flask app will handle the actual server
	select {}
}
