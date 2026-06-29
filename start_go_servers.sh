#!/bin/bash
# Start Go Servers for Cloud-Reaper
# This script starts the Go background services that work with the Python application

set -e

echo "🚀 Starting Go Servers for Cloud-Reaper..."
echo "========================================"

# Set environment variables for Go servers
export GO_TASK_MANAGER_HOST=${GO_TASK_MANAGER_HOST:-localhost}
export GO_TASK_MANAGER_PORT=${GO_TASK_MANAGER_PORT:-7071}
export GO_WEBSOCKET_HOST=${GO_WEBSOCKET_HOST:-localhost}
export GO_WEBSOCKET_PORT=${GO_WEBSOCKET_PORT:-7072}
export GO_RATELIMITER_HOST=${GO_RATELIMITER_HOST:-localhost}
export GO_RATELIMITER_PORT=${GO_RATELIMITER_PORT:-7073}
export GO_BRIDGE_HOST=${GO_BRIDGE_HOST:-localhost}
export GO_BRIDGE_PORT=${GO_BRIDGE_PORT:-7070}

# Function to check if a binary exists
check_binary() {
    if [ ! -f "$1" ]; then
        echo "❌ Binary not found: $1"
        echo "Please build the Go servers first: cd src/engine-go && go build -o ../../bin/ ./cmd/..."
        exit 1
    fi
}

# Check for Go binaries
echo "🔍 Checking Go binaries..."
BINARY_DIR="./bin"
if [ ! -d "$BINARY_DIR" ]; then
    echo "Creating bin directory..."
    mkdir -p "$BINARY_DIR"
fi

# Check if binaries exist, if not build them
if [ ! -f "$BINARY_DIR/taskserver" ] || [ ! -f "$BINARY_DIR/websocketserver" ] || [ ! -f "$BINARY_DIR/ratelimitserver" ]; then
    echo "🔨 Building Go servers..."
    cd src/engine-go
    go build -o ../../bin/taskserver ./cmd/taskserver
    go build -o ../../bin/websocketserver ./cmd/websocketserver
    go build -o ../../bin/ratelimitserver ./cmd/ratelimitserver
    cd ../..
    echo "✅ Go servers built successfully"
fi

# Start Go Task Manager Server
echo "📋 Starting Go Task Manager Server on port $GO_TASK_MANAGER_PORT..."
$BINARY_DIR/taskserver -port=$GO_TASK_MANAGER_PORT &
TASK_PID=$!
echo "   Task Manager PID: $TASK_PID"

# Wait a moment for task server to start
sleep 2

# Start Go WebSocket Batcher Server
echo "📡 Starting Go WebSocket Batcher Server on port $GO_WEBSOCKET_PORT..."
$BINARY_DIR/websocketserver -port=$GO_WEBSOCKET_PORT &
WS_PID=$!
echo "   WebSocket Batcher PID: $WS_PID"

# Wait a moment for WebSocket server to start
sleep 2

# Start Go Rate Limiter Server
echo "⚡ Starting Go Rate Limiter Server on port $GO_RATELIMITER_PORT..."
$BINARY_DIR/ratelimitserver -port=$GO_RATELIMITER_PORT &
RATE_PID=$!
echo "   Rate Limiter PID: $RATE_PID"

# Save PIDs for cleanup
echo "$TASK_PID" > .task_server.pid
echo "$WS_PID" > .websocket_server.pid
echo "$RATE_PID" > .ratelimit_server.pid

echo ""
echo "✅ All Go servers started successfully!"
echo "========================================"
echo "Task Manager: http://$GO_TASK_MANAGER_HOST:$GO_TASK_MANAGER_PORT"
echo "WebSocket Batcher: http://$GO_WEBSOCKET_HOST:$GO_WEBSOCKET_PORT"
echo "Rate Limiter: http://$GO_RATELIMITER_HOST:$GO_RATELIMITER_PORT"
echo ""
echo "To stop servers, run: ./stop_go_servers.sh"
echo "To start the Python application, run: python main.py"
echo ""

# Health check
echo "🔍 Performing health checks..."
sleep 2

# Check Task Manager
if curl -s http://$GO_TASK_MANAGER_HOST:$GO_TASK_MANAGER_PORT/health > /dev/null 2>&1; then
    echo "✅ Task Manager is healthy"
else
    echo "⚠️  Task Manager health check failed"
fi

# Check WebSocket Batcher
if curl -s http://$GO_WEBSOCKET_HOST:$GO_WEBSOCKET_PORT/health > /dev/null 2>&1; then
    echo "✅ WebSocket Batcher is healthy"
else
    echo "⚠️  WebSocket Batcher health check failed"
fi

# Check Rate Limiter
if curl -s http://$GO_RATELIMITER_HOST:$GO_RATELIMITER_PORT/health > /dev/null 2>&1; then
    echo "✅ Rate Limiter is healthy"
else
    echo "⚠️  Rate Limiter health check failed"
fi

echo ""
echo "🎉 Go servers are ready for integration with Python application!"
