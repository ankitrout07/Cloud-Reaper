#!/bin/bash

# Script to start the Go Task Manager Server
# This should be run before starting the main Python application

cd "$(dirname "$0")/../"
echo "Building Go Task Manager Server..."
go build -o ../../bin/task-server ./cmd/taskserver/main.go

if [ $? -eq 0 ]; then
    echo "Build successful. Starting task server on port 7071..."
    ../../bin/task-server --port=7071
else
    echo "Build failed. Please check for compilation errors."
    exit 1
fi