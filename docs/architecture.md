# Cloud-Reaper System Architecture

Welcome to the central system architecture spec for **Cloud-Reaper**. This document details the hybrid design, data flow, and codebase layouts.

## Core Design Philosophy

Cloud-Reaper utilizes a unique hybrid design to combine the best capabilities of both developer ecosystems:
- **Go Performance Core (`engine-go`)**: Written in Go 1.24+ for massive parallel scaling and memory efficiency. Scrapers query Azure/AWS/GCP/Kubernetes APIs concurrently using lightweight Goroutines and write raw asset snapshots directly into PostgreSQL.
- **Python FinOps Intelligence Layer (`reaper`)**: Written in Python 3.12+ for scientific computing, machine learning, and high-level orchestration. Implements VM rightsizing via reinforcement learning agents and ARIMA forecasting engines.

## High-Velocity Scanning Core

The Go scanning core implements concurrent worker pools using:
- `sync.WaitGroup` worker models to query cloud APIs without blocking.
- Token-bucket rate limiters (`golang.org/x/time/rate`) to strictly respect cloud provider API quotas.
- Safe PostgreSQL insertion pools using optimized transactions.

## Python FinOps Intelligence Layer

The Python layer consumes database states to:
- Perform time-series ARIMA prediction and seasonal decomposition of compute workloads.
- Run Q-learning reinforcement learning models to determine target virtual VM sizing families.
- Generate dynamic infrastructure designs via Google's `google-genai` and Gemini-3-flash cognitive models.
