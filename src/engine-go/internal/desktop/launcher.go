//go:build !headless

package desktop

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	webview "github.com/webview/webview_go"
)

func FindAvailablePort() int {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 5001
	}
	defer listener.Close()
	return listener.Addr().(*net.TCPAddr).Port
}

func Run() {
	port := FindAvailablePort()
	appData := os.Getenv("APPDATA")
	if appData == "" {
		appData = os.Getenv("HOME")
	}

	runtimeDir := filepath.Join(appData, "CloudReaper", "runtime")
	pythonExe := filepath.Join(runtimeDir, "python", "python.exe")
	appScript := filepath.Join(runtimeDir, "src", "reaper", "web", "app.py")

	ipcName := fmt.Sprintf("cloudreaper-ipc-%d.sock", time.Now().UnixNano())
	ipcPath := filepath.Join(os.TempDir(), ipcName)

	// Subprocess Management: Initialize background worker execution
	cmd := exec.Command(pythonExe, appScript)
	cmd.Env = append(os.Environ(),
		fmt.Sprintf("PORT=%d", port),
		"PRODUCTION_DESKTOP_MODE=TRUE",
		fmt.Sprintf("IPC_PATH=%s", ipcPath),
	)

	processStarted := false
	if err := cmd.Start(); err != nil {
		log.Fatalf("Fatal: Failed to map internal worker infrastructure: %v", err)
	}
	processStarted = true

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Ensure subprocess cleanup on exit
	defer func() {
		// Shutdown HTTP server gracefully
		cancel()
		
		if processStarted && cmd.Process != nil {
			_ = cmd.Process.Kill()
			_ = cmd.Wait()
		}
		os.Remove(ipcPath)
	}()

	// Start Go Reverse Proxy to UDS
	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = "http"
			req.URL.Host = "python-backend"
		},
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				return net.Dial("unix", ipcPath)
			},
		},
	}

	// Create HTTP server with proper shutdown support
	server := &http.Server{
		Addr:    fmt.Sprintf("127.0.0.1:%d", port),
		Handler: proxy,
	}

	// Start server in goroutine with context support
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Printf("HTTP server error: %v", err)
		}
	}()

	// Graceful shutdown goroutine
	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = server.Shutdown(shutdownCtx)
	}()

	// Active Health Check Polling Routine Loop
	backendAddr := fmt.Sprintf("http://127.0.0.1:%d", port)
	ready := false
	for i := 0; i < 30; i++ {
		resp, err := http.Get(backendAddr)
		if err == nil && resp.StatusCode == 200 {
			ready = true
			resp.Body.Close()
			break
		}
		if resp != nil {
			resp.Body.Close()
		}
		time.Sleep(200 * time.Millisecond)
	}

	if !ready {
		log.Fatal("Fatal: Application worker initialization timeout exceeded.")
	}

	// Native Windows Desktop WebView Frame Initialization
	w := webview.New(false)
	if w == nil {
		log.Fatal("Fatal: Failed to initialize webview")
	}
	w.SetTitle("Cloud-Reaper: FinOps Intelligence Suite")
	w.SetSize(1280, 800, webview.HintNone)
	w.Navigate(backendAddr)

	// Intercept Window Execution Loop for Graceful Shutdown
	w.Run()
}
