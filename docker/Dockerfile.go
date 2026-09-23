# ==============================================================================
# Go Microservices Dockerfile for Cloud-Reaper
# Builds a lightweight Alpine image with all Go microservice binaries
# ==============================================================================

FROM golang:1.24-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

COPY src/engine-go/go.mod src/engine-go/go.sum ./
RUN go mod download

COPY src/engine-go/ ./

# Build all Go microservices and the core reaper-engine bridge
RUN mkdir -p /build/bin && \
    CGO_ENABLED=0 go build -tags=cli -ldflags="-s -w" -o /build/bin/reaper-engine . && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/taskserver ./cmd/taskserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/websocketserver ./cmd/websocketserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/ratelimitserver ./cmd/ratelimitserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/ragserver ./cmd/ragserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/calculatorserver ./cmd/calculatorserver && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /build/bin/anomalyserver ./cmd/anomalyserver

# Minimal Alpine runtime
FROM alpine:3.20

WORKDIR /app

RUN apk add --no-cache wget ca-certificates tzdata

# Copy all compiled binaries to system PATH
COPY --from=builder /build/bin/* /usr/local/bin/

# Default entrypoint to reaper-engine HTTP bridge (override in docker-compose for each microservice)
CMD ["reaper-engine", "--mode", "serve", "--port", "7070"]
