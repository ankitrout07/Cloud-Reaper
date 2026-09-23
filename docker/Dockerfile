# ==============================================================================
# Multi-Stage Dockerfile for Cloud-Reaper
# Stage 1: Build all Go Performance Microservices & Core Engine
# Stage 2: Python 3.12 Intelligence Layer, FastAPI ASGI Dashboard & WeasyPrint
# ==============================================================================

# --- Stage 1: Go Services Builder ---
FROM golang:1.24-alpine AS go-builder

WORKDIR /app

# Install build tools
RUN apk add --no-cache git

# Cache Go modules
COPY src/engine-go/go.mod src/engine-go/go.sum ./
RUN go mod download

# Copy full Go source tree
COPY src/engine-go/ ./

# Build all Go binaries in static headless/CLI mode
RUN mkdir -p /build/bin && \
    CGO_ENABLED=0 go build -tags=cli -ldflags="-s -w" -o /build/bin/reaper-engine . && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/taskserver ./cmd/taskserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/websocketserver ./cmd/websocketserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/ratelimitserver ./cmd/ratelimitserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/ragserver ./cmd/ragserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/calculatorserver ./cmd/calculatorserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/anomalyserver ./cmd/anomalyserver

# --- Stage 2: Python Intelligence Layer & Web Application ---
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for WeasyPrint PDF generation and container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Go performance binaries from builder stage
COPY --from=go-builder /build/bin/ /app/bin/
ENV PATH="/app/bin:${PATH}"

# Copy application source code and configuration
COPY src/ ./src/
COPY docs/ ./docs/
COPY main.py bootstrap.py .env.example ./

# Copy and set up container entrypoint
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Environment settings
ENV PYTHONPATH=/app/src \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5001 \
    DATABASE_URL=sqlite:////app/data/reaper.db \
    PYTHONUNBUFFERED=1

# Expose web dashboard port
EXPOSE 5001

# Volume for persistent SQLite database state & audit logs
VOLUME ["/app/data"]

# Healthcheck monitoring the FastAPI dashboard
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5001/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "reaper.web.app_async:socket_app", "--host", "0.0.0.0", "--port", "5001"]
