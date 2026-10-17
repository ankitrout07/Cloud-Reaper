# ==============================================================================
# Go Microservices Dockerfile for Cloud-Reaper
# Builds a distroless image with all Go microservice binaries
# Builder: golang:1.24-alpine3.21  (Go 1.24 stable, patched Alpine)
# Runtime: gcr.io/distroless/static-debian12:nonroot (zero-shell, CVE-minimal)
#          All binaries are CGO_ENABLED=0 (fully static) — distroless is ideal.
# ==============================================================================

FROM golang:1.24-alpine3.21 AS builder

WORKDIR /app

RUN apk upgrade --no-cache && apk add --no-cache git

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

# ── Distroless runtime ────────────────────────────────────────────────────────
# gcr.io/distroless/static-debian12 contains ONLY:
#   ca-certificates, tzdata, /etc/passwd, /tmp
# No shell, no package manager, no wget — minimal CVE surface.
# nonroot variant runs as uid 65532 by default.
FROM gcr.io/distroless/static-debian12:nonroot

# Copy all compiled static binaries
COPY --from=builder /build/bin/* /usr/local/bin/

# Default entrypoint to reaper-engine HTTP bridge (override in docker-compose for each microservice)
CMD ["reaper-engine", "--mode", "serve", "--port", "7070"]
