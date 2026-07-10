# WebSocket Batcher API Endpoints

## Overview
The enhanced WebSocket system provides both HTTP REST endpoints and direct WebSocket connections for real-time metrics streaming and batched message processing.

## Base URL
```
http://localhost:7072
```

## HTTP REST Endpoints

### Health Check
**Endpoint:** `GET /health`

**Description:** Health check endpoint for the WebSocket batcher service.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "service": "websocket_batcher"
  }
}
```

---

### Batching Endpoints

#### Send Batched Message
**Endpoint:** `POST /api/ws/batch/send`

**Description:** Queue a message for batched emission via the WebSocket batcher.

**Request Body:**
```json
{
  "event": "metric_update",
  "data": {
    "time": "2024-01-01T00:00:00Z",
    "value": 123.45
  },
  "room": "optional_room_name"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "queued"
  }
}
```

---

#### Flush All Batches
**Endpoint:** `POST /api/ws/batch/flush`

**Description:** Immediately flush all pending batches.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "flushed"
  }
}
```

---

#### Get Batcher Statistics
**Endpoint:** `GET /api/ws/batch/stats`

**Description:** Get current statistics and performance metrics for the batcher.

**Response:**
```json
{
  "success": true,
  "data": {
    "running": true,
    "total_queued": 42,
    "dropped_count": 0,
    "sent_count": 15234,
    "batch_count": 3,
    "batch_interval_ms": 150,
    "max_batch_size": 30,
    "max_queue_size": 1000,
    "enable_compression": true,
    "adaptive_batching": true,
    "max_concurrent_flush": 10,
    "buffer_pool_size": 100,
    "messages_per_second": 856.5,
    "compression": {
      "total_messages": 15234,
      "compressed_size": 2048576,
      "original_size": 8192000,
      "compression_ratio": 0.25,
      "total_savings": 6143424
    }
  }
}
```

---

#### Update Batcher Configuration
**Endpoint:** `POST /api/ws/batch/config`

**Description:** Update batcher configuration parameters dynamically.

**Request Body:**
```json
{
  "batch_interval_ms": 150,
  "max_batch_size": 30,
  "max_queue_size": 1000,
  "enable_compression": true,
  "adaptive_batching": true,
  "max_concurrent_flush": 10,
  "buffer_pool_size": 100
}
```

**Response:** Returns updated statistics (same format as `/api/ws/batch/stats`)

---

#### Stop Batcher
**Endpoint:** `POST /api/ws/batch/stop`

**Description:** Stop the batcher and flush all pending batches if configured.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "stopped"
  }
}
```

---

#### Start Batcher
**Endpoint:** `POST /api/ws/batch/start`

**Description:** Start the batcher if it was previously stopped.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "started"
  }
}
```

---

### Metrics Broadcaster Endpoints

#### WebSocket Connection
**Endpoint:** `GET /ws/metrics`

**Description:** Direct WebSocket connection for real-time metrics streaming.

**Query Parameters:**
- `room` (optional): Room name for targeted updates
- `client_id` (optional): Custom client ID

**Example:**
```
ws://localhost:7072/ws/metrics?room=dashboard&client_id=my_client
```

**Message Format (Server -> Client):**
```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "metric": "cpu_usage",
  "value": 75.5,
  "metadata": {
    "host": "server1",
    "region": "us-east-1"
  }
}
```

---

#### Get Connected Clients
**Endpoint:** `GET /api/ws/clients`

**Description:** Get information about all currently connected WebSocket clients.

**Response:**
```json
{
  "success": true,
  "data": {
    "clients": [
      {
        "id": "20240101-120000-abc12345",
        "connected": "2024-01-01T12:00:00Z",
        "room": "dashboard"
      }
    ],
    "count": 1
  }
}
```

---

#### Broadcast Metric
**Endpoint:** `POST /api/ws/broadcast`

**Description:** Broadcast a metric update directly to WebSocket clients (bypasses batching).

**Request Body:**
```json
{
  "metric": "cpu_usage",
  "value": 75.5,
  "room": "dashboard",
  "metadata": {
    "host": "server1",
    "region": "us-east-1"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "broadcasted"
  }
}
```

---

## Integration Architecture

### Automatic Broadcasting
When messages are sent via `/api/ws/batch/send` with event type `metric_update`, they are automatically broadcast to WebSocket clients if the metrics broadcaster is enabled.

### Room-Based Targeting
Both batching and broadcasting support room-based targeting:
- Batching: Include `"room"` field in request body
- Broadcasting: Include `"room"` field in request body or WebSocket connection URL

### Configuration Flow
1. Server starts on port 7072
2. Metrics broadcaster initializes automatically
3. Batcher initializes with metrics broadcaster integration
4. All endpoints become available immediately

---

## Python Bridge API

The Python bridge (`go_websocket.py`) provides convenient methods for interacting with these endpoints:

```python
from reaper.integrations.go_websocket import get_websocket_batcher

# Get batcher instance
batcher = await get_websocket_batcher()

# Batching operations
await batcher.emit("metric_update", {"time": "2024-01-01T00:00:00Z", "value": 123.45}, room="dashboard")
await batcher.flush_all()
stats = await batcher.get_statistics()
await batcher.update_config(batch_interval_ms=200, enable_compression=True)

# WebSocket client operations
ws_client = await batcher.create_websocket_client(room="dashboard")
await ws_client.connect()
ws_client.add_message_handler(lambda data: print(data))
await ws_client.listen()

# Direct broadcasting
await batcher.broadcast_metric("cpu_usage", 75.5, room="dashboard")

# Client management
clients = await batcher.get_connected_clients()
```

---

## Performance Features

### Adaptive Batching
- Automatically adjusts batch size and timing based on message load
- High load (>1000 msg/s): Increases batch size and interval
- Low load (<100 msg/s): Decreases batch size and interval for lower latency

### Compression
- Gzip compression enabled by default
- Reduces bandwidth usage by 60-80%
- Disabled automatically if compression doesn't help

### Concurrent Flush Control
- Semaphore-based limiting of concurrent flush operations
- Prevents resource exhaustion under high load
- Configurable via `max_concurrent_flush`

### Memory Optimization
- Buffer pooling reduces allocation overhead
- Configurable pool size for memory tuning
- Automatic cleanup of disconnected clients

---

## Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message here"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid JSON, missing parameters)
- `405`: Method not allowed
- `500`: Internal server error

---

## Monitoring

### Key Metrics to Monitor
- `messages_per_second`: Current message throughput
- `total_queued`: Number of messages waiting to be batched
- `dropped_count`: Number of messages dropped due to full queue
- `sent_count`: Total messages successfully sent
- `compression_ratio`: Compression effectiveness (lower is better)
- `connected_clients`: Number of active WebSocket connections

### Health Check Strategy
1. Monitor `/health` endpoint for service availability
2. Monitor `/api/ws/batch/stats` for performance metrics
3. Monitor `/api/ws/clients` for connection health
4. Set up alerts for `dropped_count` > 0 or high queue sizes

---

## Security Considerations

### Current Implementation
- No authentication/authorization (development mode)
- Allows connections from any origin
- Suitable for internal/trusted networks only

### Production Recommendations
1. Add authentication middleware
2. Implement origin checking for WebSocket connections
3. Add rate limiting for HTTP endpoints
4. Enable TLS/SSL for production deployments
5. Add request validation and sanitization

---

## Deployment

### Start the Server
```bash
cd /home/ankit/git/Cloud-Reaper/src/engine-go
./websocketserver -port 7072
```

### Systemd Service Example
```ini
[Unit]
Description=Go WebSocket Batcher Server
After=network.target

[Service]
Type=simple
User=cloud-reaper
WorkingDirectory=/home/ankit/git/Cloud-Reaper/src/engine-go
ExecStart=/home/ankit/git/Cloud-Reaper/src/engine-go/websocketserver -port 7072
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Docker Deployment
```dockerfile
FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY . .
RUN go build -o websocketserver ./cmd/websocketserver

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/websocketserver .
EXPOSE 7072
CMD ["./websocketserver"]
```

---

## Testing

### Manual Testing with curl
```bash
# Health check
curl http://localhost:7072/health

# Send batched message
curl -X POST http://localhost:7072/api/ws/batch/send \
  -H "Content-Type: application/json" \
  -d '{"event":"metric_update","data":{"time":"2024-01-01T00:00:00Z","value":123.45}}'

# Get statistics
curl http://localhost:7072/api/ws/batch/stats

# Get connected clients
curl http://localhost:7072/api/ws/clients

# Broadcast metric
curl -X POST http://localhost:7072/api/ws/broadcast \
  -H "Content-Type: application/json" \
  -d '{"metric":"cpu_usage","value":75.5,"room":"dashboard"}'
```

### WebSocket Testing
```javascript
// Browser or Node.js WebSocket client
const ws = new WebSocket('ws://localhost:7072/ws/metrics?room=dashboard');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

ws.onopen = () => {
  console.log('Connected to WebSocket');
};
```

---

## Version Information
- **API Version:** 1.0
- **Go Version:** 1.25.0
- **Last Updated:** 2026-07-10
- **Status:** Production Ready
