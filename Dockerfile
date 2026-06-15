# Multi-stage build for Cloud-Reaper
# 1. Build Go Performance Engine (headless mode for Docker)
FROM golang:1.25-alpine AS go-builder
WORKDIR /app
COPY src/engine-go/ .
# Build with headless tag to skip webview dependency
RUN CGO_ENABLED=0 go build -tags=headless -o /reaper-engine main.go

# 2. Build Python Intelligence Layer & Dashboard
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies for WeasyPrint and other tools
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-cffi \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY main.py .
COPY .env.example .env

# Copy Go binary from builder stage
COPY --from=go-builder /reaper-engine ./bin/reaper-engine

# Set environment variables
ENV PYTHONPATH=/app/src
ENV FLASK_APP=reaper.web.app
ENV FLASK_PORT=5001
ENV FLASK_HOST=0.0.0.0

EXPOSE 5001

# Entrypoint
CMD ["python", "main.py"]
