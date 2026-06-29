# Go Services Dockerfile for Cloud-Reaper
# This is a template - each service will use this with different commands

FROM golang:1.25-alpine AS builder

WORKDIR /app

# Copy Go source code
COPY src/engine-go/ .

# Build all Go servers
RUN CGO_ENABLED=0 go build -o taskserver ./cmd/taskserver
RUN CGO_ENABLED=0 go build -o websocketserver ./cmd/websocketserver
RUN CGO_ENABLED=0 go build -o ratelimitserver ./cmd/ratelimitserver

# Final stage - minimal alpine image
FROM alpine:latest

WORKDIR /app

# Install wget for health checks
RUN apk add --no-cache wget

# Copy binaries from builder
COPY --from=builder /app/taskserver .
COPY --from=builder /app/websocketserver .
COPY --from=builder /app/ratelimitserver .

# Default command (will be overridden in docker-compose)
CMD ["sh", "-c", "echo 'Go services container ready. Use docker-compose to start specific services.'"]
