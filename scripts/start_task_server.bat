@echo off
REM Script to start the Go Task Manager Server on Windows
REM This should be run before starting the main Python application

cd /d "%~dp0..\"
echo Building Go Task Manager Server...
go build -o ..\..\bin\task-server.exe .\cmd\taskserver\main.go

if %ERRORLEVEL% EQU 0 (
    echo Build successful. Starting task server on port 7071...
    ..\..\bin\task-server.exe --port=7071
) else (
    echo Build failed. Please check for compilation errors.
    exit /b 1
)