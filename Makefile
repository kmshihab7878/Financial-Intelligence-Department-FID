# AIS Makefile

.PHONY: help setup build up down logs test test-cov lint typecheck clean health format check docs docs-serve security

help:
	@echo "AIS - Autonomous Investment Swarm"
	@echo ""
	@echo "Development:"
	@echo "  make setup      - Setup development environment"
	@echo "  make test       - Run unit tests"
	@echo "  make test-cov   - Run tests with coverage"
	@echo "  make lint       - Run linter and format check"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make format     - Auto-format code with ruff"
	@echo "  make check      - Run all quality checks (lint + typecheck + test)"
	@echo "  make security   - Run security scans"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs       - Build documentation site"
	@echo "  make docs-serve - Serve documentation locally"
	@echo ""
	@echo "Docker:"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start services"
	@echo "  make down       - Stop services"
	@echo "  make logs       - View service logs"
	@echo "  make health     - Run health check"
	@echo "  make clean      - Clean up"

# ── Development ──────────────────────────────────────────────

setup:
	@echo "Setting up AIS development environment..."
	pip install -r requirements.txt
	pip install -e ".[dev]"
	pip install -r requirements-docs.txt
	pre-commit install
	mkdir -p data logs

test:
	@echo "Running AIS unit tests..."
	pytest tests/unit/ -v

test-cov:
	@echo "Running AIS tests with coverage..."
	pytest tests/unit/ --cov=src/aiswarm --cov-report=term-missing --cov-fail-under=83

lint:
	@echo "Linting AIS..."
	ruff check src/ tests/unit/
	ruff format --check src/ tests/unit/

typecheck:
	@echo "Type checking AIS..."
	mypy src/aiswarm/ --ignore-missing-imports

format:
	@echo "Formatting code..."
	ruff format src/ tests/unit/
	ruff check --fix src/ tests/unit/

check: lint typecheck test-cov
	@echo "All checks passed."

security:
	@echo "Running security scans..."
	pip-audit --strict --ignore-vuln PYSEC-2024-*
	bandit -r src/aiswarm/ -ll

# ── Documentation ────────────────────────────────────────────

docs:
	@echo "Building documentation..."
	mkdocs build --strict

docs-serve:
	@echo "Serving documentation at http://localhost:8000..."
	mkdocs serve

# ── Docker ───────────────────────────────────────────────────

build:
	@echo "Building AIS Docker images..."
	docker compose build

up:
	@echo "Starting AIS services..."
	docker compose up -d
	@echo "Access points:"
	@echo "  API:        http://localhost:8000"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana:    http://localhost:3000"

down:
	@echo "Stopping AIS services..."
	docker compose down

logs:
	docker compose logs -f

health:
	@echo "Checking AIS health..."
	python scripts/health_check.py

clean:
	@echo "Cleaning up..."
	docker compose down -v
	rm -rf __pycache__/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage site/
