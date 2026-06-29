#!/bin/bash

# Script to start the Go Rate Limiter Server
# This should be run before starting the main Python application

cd "$(dirname "$0")/../"
echo "Building Go Rate Limiter Server..."
go build -o ../../bin/rate-limit-server ./cmd/ratelimitserver/main.go

if [ $? -eq 0 ]; then
    echo "Build successful. Starting rate limiter server on port 7073..."
    ../../bin/rate-limit-server --port=7073
else
    echo "Build failed. Please check for compilation errors."
    exit 1
fi