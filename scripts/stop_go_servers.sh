#!/bin/bash
# Stop Go Servers for Cloud-Reaper
# This script stops the Go background services

echo "🛑 Stopping Go Servers for Cloud-Reaper..."
echo "========================================"

# Function to kill process by PID file
kill_process() {
    local pid_file=$1
    local service_name=$2
    
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $service_name (PID: $pid)..."
            kill "$pid"
            rm "$pid_file"
            echo "✅ $service_name stopped"
        else
            echo "⚠️  $service_name process not running (PID: $pid)"
            rm "$pid_file"
        fi
    else
        echo "⚠️  No PID file found for $service_name"
    fi
}

# Stop Task Manager Server
kill_process ".task_server.pid" "Task Manager"

# Stop WebSocket Batcher Server
kill_process ".websocket_server.pid" "WebSocket Batcher"

# Stop Rate Limiter Server
kill_process ".ratelimit_server.pid" "Rate Limiter"

# Additional cleanup - kill any remaining processes on the ports
echo "🧹 Performing additional cleanup..."
for port in 7070 7071 7072 7073; do
    pid=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "Killing process on port $port (PID: $pid)"
        kill -9 "$pid" 2>/dev/null || true
    fi
done

echo ""
echo "✅ All Go servers stopped successfully!"
echo "========================================"
