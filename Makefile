.PHONY: help install venv build test test-python test-go lint lint-python lint-go run clean

export PYTHONPATH := $(shell pwd)/src

VENV_PYTHON := ./venv/bin/python
VENV_PIP := ./venv/bin/pip
GO_LINT := ./bin/golangci-lint

# Default target
help:
	@echo "Cloud-Reaper Development Commands:"
	@echo "  install    Install dependencies (Python & Go) into venv"
	@echo "  build      Build Go engine"
	@echo "  test       Run all tests"
	@echo "  lint       Run all linters"
	@echo "  run        Run the application locally"
	@echo "  clean      Clean build artifacts"

install: venv
	$(VENV_PIP) install -r requirements.txt -r requirements-dev.txt
	cd src/engine-go && go mod download
	GOBIN=$(shell pwd)/bin go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

venv:
	@if [ ! -d "venv" ]; then python3 -m venv venv; fi
	$(VENV_PYTHON) -m pip install --upgrade pip

build:
	mkdir -p bin
	cd src/engine-go && go build -o ../../bin/reaper-engine main.go

test: test-python test-go

test-python: install
	$(VENV_PYTHON) -m pytest

test-go:
	cd src/engine-go && go test -v ./...

lint: lint-python lint-go

lint-python: install
	./venv/bin/python -m ruff check src/reaper tests
	./venv/bin/python -m mypy src/reaper tests --ignore-missing-imports || true

lint-go: install
	cd src/engine-go && ../../bin/golangci-lint run ./...

fmt: fmt-python fmt-go

fmt-python: install
	$(VENV_PYTHON) -m ruff format src/reaper tests
	$(VENV_PYTHON) -m ruff check --fix src/reaper tests

fmt-go:
	cd src/engine-go && go fmt ./...
	cd src/engine-go && ../../bin/golangci-lint run --fix ./...


run: install build
	./scripts/reap.sh

clean:
	rm -rf bin/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
