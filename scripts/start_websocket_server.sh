#!/bin/bash

# Script to start the Go WebSocket Batcher Server
# This should be run before starting the main Python application

cd "$(dirname "$0")/../"
echo "Building Go WebSocket Batcher Server..."
go build -o ../../bin/websocket-server ./cmd/websocketserver/main.go

if [ $? -eq 0 ]; then
    echo "Build successful. Starting WebSocket batcher server on port 7072..."
    ../../bin/websocket-server --port=7072
else
    echo "Build failed. Please check for compilation errors."
    exit 1
fi