.PHONY: help install build test lint run clean

export PYTHONPATH := $(shell pwd)/src

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
	cd src/engine-go && go mod download

build:
	mkdir -p bin
	cd src/engine-go && go build -o ../../bin/reaper-engine main.go

test: test-python test-go

test-python:
	pytest

test-go:
	cd src/engine-go && go test -v ./...

lint: lint-python lint-go

lint-python:
	ruff check src/reaper
	mypy src/reaper --ignore-missing-imports

lint-go:
	cd src/engine-go && golangci-lint run ./...

run: build
	./scripts/reap.sh

clean:
	rm -rf bin/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
