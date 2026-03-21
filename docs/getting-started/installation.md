# Installation

## Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended)
- **Redis** (for control state coordination)
- **Docker and Docker Compose** (optional, for full stack deployment)

## Install from Source

```bash
# Clone the repository
git clone https://github.com/kmshihab7878/Autonomous-Investment-Swarm.git
cd Autonomous-Investment-Swarm

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with dependencies
pip install -r requirements.txt
pip install -e .
```

### Development Installation

For running tests, linting, and type checking:

```bash
pip install -e ".[dev]"
pre-commit install
```

Verify the development installation:

```bash
make check  # Runs lint + typecheck + tests
```

## Docker Installation

```bash
# Configure environment
cp .env.example .env
# Edit .env — set at minimum:
#   AIS_RISK_HMAC_SECRET
#   AIS_DB_PASSWORD
#   GF_ADMIN_PASSWORD

# Build and start all services
docker compose up --build
```

This starts:

| Service | Port | Purpose |
|---------|------|---------|
| `ais-api` | 8000 | FastAPI control plane |
| `ais-loop` | 9002 | Trading loop (metrics) |
| `redis` | 6379 | Control state |
| `postgres` | 5432 | Database |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Dashboard |
| `alertmanager` | 9093 | Alert routing |
| `pushgateway` | 9091 | Backtest metrics |

## Redis Setup

AIS uses Redis for control state (pause/resume/kill). If not using Docker:

```bash
# macOS
brew install redis
redis-server

# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# Or via Docker
docker run -d -p 6379:6379 redis:7-alpine
```

## Verify Installation

```bash
# Check the CLI works
python -m aiswarm --help

# Run the test suite
pytest tests/unit/ -v

# Check API can start
AIS_RISK_HMAC_SECRET=test uvicorn aiswarm.api.app:app --app-dir src
# Visit http://localhost:8000/health
```
