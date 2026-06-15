//go:build !headless

package desktop

import (
	"fmt"
	"log"
	"net"
	"net/http"
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

	// Subprocess Management: Initialize background worker execution
	cmd := exec.Command(pythonExe, appScript)
	cmd.Env = append(os.Environ(),
		fmt.Sprintf("PORT=%d", port),
		"PRODUCTION_DESKTOP_MODE=TRUE",
	)

	if err := cmd.Start(); err != nil {
		log.Fatalf("Fatal: Failed to map internal worker infrastructure: %v", err)
	}

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
		time.Sleep(200 * time.Millisecond)
	}

	if !ready {
		_ = cmd.Process.Kill()
		log.Fatal("Fatal: Application worker initialization timeout exceeded.")
	}

	// Native Windows Desktop WebView Frame Initialization
	w := webview.New(false)
	w.SetTitle("Cloud-Reaper: FinOps Intelligence Suite")
	w.SetSize(1280, 800, webview.HintNone)
	w.Navigate(backendAddr)

	// Intercept Window Execution Loop for Graceful Shutdown
	w.Run()
	_ = cmd.Process.Kill()
}
