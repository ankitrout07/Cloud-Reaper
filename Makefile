.PHONY: help install build test lint run clean

# Default target
help:
	@echo "Cloud-Reaper Development Commands:"
	@echo "  install    Install dependencies (Python & Go)"
	@echo "  build      Build Go engine"
	@echo "  test       Run all tests"
	@echo "  lint       Run all linters"
	@echo "  run        Run the application locally"
	@echo "  clean      Clean build artifacts"

install:
	pip install -r requirements.txt -r requirements-dev.txt
	cd engine-go && go mod download

build:
	cd engine-go && go build -o reaper-engine main.go

test: test-python test-go

test-python:
	pytest

test-go:
	cd engine-go && go test -v ./...

lint: lint-python lint-go

lint-python:
	ruff check .
	mypy collectors engine

lint-go:
	golangci-lint run ./...

run: build
	./reap.sh

clean:
	rm -f engine-go/reaper-engine
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
