# Contributing

Thank you for considering contributing to AIS.

## Development Setup

```bash
# Clone the repository
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
```

## Code Style

- **Linter/Formatter**: [Ruff](https://docs.astral.sh/ruff/) (line length 100)
- **Type Checker**: [mypy](https://mypy-lang.org/) (strict mode)
- **Type Hints**: Required on all function signatures
- **Models**: Pydantic v2 with `frozen=True`
- **Logging**: stdlib `logging` with structured JSON output

## Pull Request Requirements

Before submitting a PR, ensure all checks pass:

```bash
# Tests with coverage
pytest tests/unit/ -v --cov=src/aiswarm --cov-fail-under=83

# Lint
ruff check src/ tests/unit/
ruff format --check src/ tests/unit/

# Type check
mypy src/aiswarm/ --ignore-missing-imports
```

Or use the Makefile:

```bash
make lint && make typecheck && make test-cov
```

## Testing

- Tests live in `tests/unit/`
- Use pytest with the AAA pattern (Arrange, Act, Assert)
- Minimum 83% code coverage
- New features require corresponding tests
- Use `@pytest.mark.slow` for tests taking more than 1 second

## Project Structure

All production code lives under `src/aiswarm/`. See the [Architecture Overview](architecture/overview.md) for the module layout.

## Security

If you find a security vulnerability, do **not** open a public issue. See [SECURITY.md](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/blob/main/SECURITY.md).
