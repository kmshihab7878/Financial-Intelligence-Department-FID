# Contributing to AIS

Thank you for considering contributing to the Autonomous Investment Swarm. This guide covers the development workflow, standards, and conventions.

## Development Setup

```bash
# Clone and install
git clone https://github.com/kmshihab7878/Autonomous-Investment-Swarm.git
cd Autonomous-Investment-Swarm

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify everything works
make lint && make typecheck && make test-cov
```

## Code Style

| Tool | Purpose | Config |
|------|---------|--------|
| [Ruff](https://docs.astral.sh/ruff/) | Linting + formatting | `pyproject.toml` (line-length=100) |
| [mypy](https://mypy-lang.org/) | Type checking | `pyproject.toml` (strict=true) |

### Conventions

- **Type hints** on all function signatures (enforced by mypy strict mode)
- **Pydantic v2** with `frozen=True` for all domain models
- **stdlib `logging`** with `JsonFormatter` for structured JSON output
- **No bare `except:`** — always specify the exception type
- **No `TODO`/`FIXME`** without a linked issue number

## Pull Request Checklist

Before submitting a PR, verify all checks pass:

```bash
# Run all checks
make lint && make typecheck && make test-cov

# Or individually:
pytest tests/unit/ -v --cov=src/aiswarm --cov-fail-under=83
ruff check src/ tests/unit/
ruff format --check src/ tests/unit/
mypy src/aiswarm/ --ignore-missing-imports
```

### PR Requirements

- [ ] Tests pass with 83%+ coverage
- [ ] Lint and format clean
- [ ] mypy passes (strict mode)
- [ ] New features include corresponding tests
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)

### Commit Message Format

```
<type>(<scope>): <description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`

Scopes: `risk`, `agents`, `exchange`, `execution`, `api`, `monitoring`, `portfolio`, `quant`, `loop`

Examples:
```
feat(agents): add RSI-based strategy agent
fix(risk): correct HMAC token TTL check for edge case
docs(guides): add backtesting tutorial
test(exchange): add Binance provider unit tests
```

## Testing

- Tests live in `tests/unit/`
- Use pytest with the **AAA pattern** (Arrange, Act, Assert)
- Minimum **83% code coverage** (enforced in CI)
- New features require corresponding tests
- Use `@pytest.mark.slow` for tests taking more than 1 second
- Use `pytest.mark.parametrize` for testing multiple inputs

## Project Structure

All production code lives under `src/aiswarm/`. See the [Architecture docs](https://kmshihab7878.github.io/Autonomous-Investment-Swarm/architecture/overview/) for details.

## Building Documentation

```bash
pip install -r requirements-docs.txt
mkdocs serve   # Local preview at http://localhost:8000
mkdocs build   # Build static site
```

## Reporting Issues

- **Bugs**: Use the [bug report template](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/issues/new?template=bug_report.yml)
- **Features**: Use the [feature request template](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/issues/new?template=feature_request.yml)
- **Security**: See [SECURITY.md](SECURITY.md) — do **not** open a public issue

## Getting Help

If you have questions about contributing:

1. Check the [documentation](https://kmshihab7878.github.io/Autonomous-Investment-Swarm/)
2. Search existing [issues](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/issues)
3. Open a [discussion](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/discussions)
