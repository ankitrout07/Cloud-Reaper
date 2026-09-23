#!/bin/sh
set -e

echo "=================================================="
echo "💀 Cloud-Reaper Container Starting"
echo "=================================================="

# Ensure data directory exists for SQLite storage
mkdir -p /app/data

# Initialize / migrate database schema if using SQLite
if echo "${DATABASE_URL:-sqlite:////app/data/reaper.db}" | grep -q "sqlite"; then
    echo "📦 Initializing SQLite database schema..."
    python3 -c "
try:
    from reaper.engine.models.resources import init_db
    init_db()
    print('✅ Database schema initialized.')
except Exception as e:
    print(f'⚠️ Database auto-init notice: {e}')
"
fi

# Track background service PIDs for graceful termination
BG_PIDS=""

cleanup() {
    echo "🛑 Shutting down container processes..."
    if [ -n "$BG_PIDS" ]; then
        for pid in $BG_PIDS; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done
        wait $BG_PIDS 2>/dev/null || true
    fi
    exit 0
}

trap cleanup INT TERM

# Check if Go services should be launched locally in all-in-one mode
# By default, if GO_TASK_MANAGER_HOST is 'localhost' or '127.0.0.1', we run the built-in Go microservices
LAUNCH_LOCAL_GO="false"
if [ "${GO_TASK_MANAGER_HOST:-localhost}" = "localhost" ] || [ "${GO_TASK_MANAGER_HOST:-localhost}" = "127.0.0.1" ]; then
    LAUNCH_LOCAL_GO="true"
fi

if [ "$LAUNCH_LOCAL_GO" = "true" ]; then
    echo "🚀 Starting embedded Go microservices (All-In-One Mode)..."

    # 1. Reaper Core Engine Bridge (port 7070)
    if [ -x "/app/bin/reaper-engine" ]; then
        echo "   -> Starting reaper-engine bridge on port ${GO_BRIDGE_PORT:-7070}..."
        /app/bin/reaper-engine --mode serve --port "${GO_BRIDGE_PORT:-7070}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 2. Task Manager Server (port 7071)
    if [ -x "/app/bin/taskserver" ]; then
        echo "   -> Starting taskserver on port ${GO_TASK_MANAGER_PORT:-7071}..."
        /app/bin/taskserver -port "${GO_TASK_MANAGER_PORT:-7071}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 3. WebSocket Batcher Server (port 7072)
    if [ -x "/app/bin/websocketserver" ]; then
        echo "   -> Starting websocketserver on port ${GO_WEBSOCKET_PORT:-7072}..."
        /app/bin/websocketserver -port "${GO_WEBSOCKET_PORT:-7072}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 4. Rate Limiter Server (port 7073)
    if [ -x "/app/bin/ratelimitserver" ]; then
        echo "   -> Starting ratelimitserver on port ${GO_RATELIMITER_PORT:-7073}..."
        /app/bin/ratelimitserver -port "${GO_RATELIMITER_PORT:-7073}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 5. Hybrid RAG Search Server (port 7074)
    if [ -x "/app/bin/ragserver" ]; then
        echo "   -> Starting ragserver on port ${GO_RAG_PORT:-7074}..."
        /app/bin/ragserver -port "${GO_RAG_PORT:-7074}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 6. Cost Calculator Server (port 7075)
    if [ -x "/app/bin/calculatorserver" ]; then
        echo "   -> Starting calculatorserver on port ${GO_CALCULATOR_PORT:-7075}..."
        /app/bin/calculatorserver -port "${GO_CALCULATOR_PORT:-7075}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # 7. Anomaly Detection Server (port 7076)
    if [ -x "/app/bin/anomalyserver" ]; then
        echo "   -> Starting anomalyserver on port ${GO_ANOMALY_PORT:-7076}..."
        /app/bin/anomalyserver -port "${GO_ANOMALY_PORT:-7076}" &
        BG_PIDS="$BG_PIDS $!"
    fi

    # Brief delay for Go daemons to bind ports
    sleep 1
else
    echo "🌐 Mesh Mode: Connecting to external Go microservices at:"
    echo "   Bridge:     http://${GO_BRIDGE_HOST}:${GO_BRIDGE_PORT:-7070}"
    echo "   Task:       http://${GO_TASK_MANAGER_HOST}:${GO_TASK_MANAGER_PORT:-7071}"
    echo "   WebSocket:  http://${GO_WEBSOCKET_HOST}:${GO_WEBSOCKET_PORT:-7072}"
    echo "   RateLimit:  http://${GO_RATELIMITER_HOST}:${GO_RATELIMITER_PORT:-7073}"
    echo "   RAG:        http://${GO_RAG_HOST:-rag-server}:${GO_RAG_PORT:-7074}"
    echo "   Calculator: http://${GO_CALCULATOR_HOST:-calculator-server}:${GO_CALCULATOR_PORT:-7075}"
    echo "   Anomaly:    http://${GO_ANOMALY_HOST:-anomaly-server}:${GO_ANOMALY_PORT:-7076}"
fi

echo "✨ Cloud-Reaper environment configured. Handing off to: $@"
exec "$@"
