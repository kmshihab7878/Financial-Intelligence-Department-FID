# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-03-15

### Added
- Public release documentation (README, CONTRIBUTING, SECURITY, LICENSE)
- API specification with endpoint reference
- Architecture and agent design documentation
- GitHub issue templates and PR template
- Dependabot configuration for automated dependency updates
- CODEOWNERS for automated review assignment
- EditorConfig for consistent formatting
- CHANGELOG

### Changed
- Unified version number across package, API, and documentation
- Improved pyproject.toml metadata (classifiers, keywords, URLs)

### Removed
- Empty agent sub-package stubs (execution, evolution, forecasting, portfolio, risk)
- Empty data sub-package stubs (ingestion, normalization, feature_store)
- Unimplemented evolution module stubs (challenger, mutation, drift, rollback)
- Stub scripts replaced by CLI entry point (run_live.py, run_paper.py, run_replay.py)
- Internal release process documents

## [1.0.0] - 2025-03-14

### Added
- Core trading loop with 60-second cycle
- Multi-agent orchestration with weighted arbitration
- Momentum MA crossover strategy agent
- Funding rate contrarian strategy agent
- Risk engine with HMAC-signed approval tokens
- Kill switch with emergency order cancellation
- Drawdown guardian and leverage checks
- Portfolio allocator with exposure management
- Mandate governance system
- Session lifecycle management
- FastAPI control plane with authentication
- Prometheus metrics and monitoring
- Circuit breaker and rate limiter
- SQLite event store for audit trail
- Paper, shadow, and live execution modes
- MCP gateway integration for Aster DEX
- Quantitative tools: Kelly criterion, risk metrics, drift detection
- Docker support with health checks
- Unit test suite with 85%+ coverage
