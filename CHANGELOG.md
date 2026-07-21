# Changelog

All notable changes to the Cloud-Reaper project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] / Recent Updates

### 🏗️ Architecture & Refactoring
- **Modular Web Routing**: Refactored the `app_async.py` main application file by splitting monolithic routes into a dedicated `routers/` package. Routes are now logically separated into `settings.py`, `vault.py`, `financial.py`, `finops.py`, `resources.py`, and `cost_optimization.py` for improved maintainability.

### 🛠️ Bug Fixes & Stabilization
- **Logging Improvements**: Replaced `print()` statements with proper `logger.error()` and `logger.info()` in `azure_collector.py` and `resources.py`.
- **Startup Sequence**: Reordered initialization events in `app_async.py` to ensure the credential service initializes before the background metrics worker starts.
- **Testing Fixes**: Resolved mock context manager issues in `test_ollama_backend.py` for `httpx.Client` and dynamically patched `is_first_run` properly in `test_financial_routes.py`.

### 🔒 Security-First Architecture
- **Dry-Run Mode by Default**: Implemented dry-run mode as default behavior to prevent accidental resource modifications in production environments
- **Read-Only IAM Policies**: Updated default IAM policies to use ReadOnlyAccess/ViewOnlyAccess permissions for initial setup
- **Explicit Remediation Toggles**: Added configuration toggles (`ENABLE_REMEDIATION`, `ENABLE_ORCHESTRATION`) that require explicit user consent before enabling active remediation
- **Secondary IAM Role Prompts**: Added UI prompts for secondary IAM role deployment when users enable orchestration mode
- **Configuration Validation**: Implemented validation to prevent enabling remediation/orchestration while dry-run mode is active
- **Security Documentation**: Updated all documentation to emphasize security-first approach and proper IAM configuration

### � Security & Data Integrity
- **Eliminated All Simulated Data**: Removed all simulated/fake data fallbacks from the entire codebase. All API endpoints now fetch real data from cloud providers or return proper error responses.
- **Enhanced Error Handling**: Updated all API endpoints (`/api/finops/budget/data`, `/api/finops/budget/chart`, `/api/finops/commitments/data`, `/api/finops/issues/data`) to return 503 status codes with user-friendly error messages when cloud provider data fetch fails.
- **UI Error Guidance**: Updated frontend error handling to guide users to connect cloud providers in Settings when data fetch fails, preventing confusion about missing data.
- **Removed Placeholder Endpoints**: Deleted `/api/v1/finops/simulate/commitment` and `/api/v1/finops/simulate/policy` endpoints that returned fake simulation data.

### 🧹 Code Cleanup
- **Removed Unused Classes**: Deleted `ProportionalAllocator` class from `economics.py` (placeholder with no implementation).
- **Removed Test-Only Code**: Deleted `PredictiveScalingEngine` class from `workload.py` (only used in test block).
- **Cleaned Up Imports**: Removed unused ARIMA import from `workload.py` after PredictiveScalingEngine removal.
- **Azure Collector Cleanup**: Removed simulated data fallbacks from `get_cost_governance_issues` and `get_active_commitments` methods.
- **Code Reduction**: Removed ~120 lines of unused/simulated code across the codebase.

### �🚀 Performance Improvements
- **Dependency Upgrades**: Upgraded `ruff` linting tool to the latest version to ensure faster and more reliable code linting, formatting, and static analysis across the Python codebase.
- **Project Stabilization**: Extensive stabilization efforts applied across the hybrid Python/Go core, optimizing execution paths, reducing memory footprints, and addressing performance bottlenecks in resource scraping and telemetry ingestion.

### 🛠️ Bug Fixes & Stabilization
- **Cloud Verification Logic**: Iterative improvements to the multi-cloud provider verification mechanisms. This ensures more robust authentication, precise error handling, and highly accurate resource fetching from Azure, AWS, and GCP APIs.
- **Vault Dynamics & Log Retention**: Enhanced the security vault dynamics with improved log retention policies. This solidifies the cryptographic audit trails, ensuring tamper-proof logs are efficiently retained without causing unbounded database growth.
- **Automated Quality Gates**: Continuous auto-fixing of formatting and linting errors via GitHub Actions, maintaining strict code quality standards and preventing syntax-related regressions from reaching the main branch.

### 🎨 UI/UX Enhancements
- **Professional Aesthetic Redesign**: Completely overhauled the Vault and Cloud Provider integration UI. Implemented high-fidelity glassmorphism, dynamic color schematics, and an adaptive light/dark mode for a premium user experience.
- **Color Schematics**: Fine-tuned the color palettes (cyan glows, slate tones) across the dashboard for better contrast, readability, and modern aesthetics.
- **Dashboard Optimization**: Removed excessive and redundant system architecture blocks from the main dashboard (`index.html`) to clean up the interface and focus on core metrics.

### 📝 Documentation
- **Comprehensive Rewrite**: Full rewrite of the project `README.md`, introducing clear architectural diagrams, technology stack breakdowns, Docker deployment guides, and a complete API reference.
- **Feature Documentation**: Added detailed explanations for the Cost-Bounded Performance Copilot, RAG Documentation Search, Cryptographic Audit Trails, and Vault Secret Management.
- **Changelog Tracking**: Introduced a dedicated `CHANGELOG.md` to thoroughly track and explain all project updates, performance optimizations, and bug fixes.
