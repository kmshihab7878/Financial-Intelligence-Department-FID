# AIS application image — multi-stage build.

# Stage 1: Builder — compile native extensions
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 600 --retries 10 \
    --prefix=/install -r requirements.txt

# Stage 2: Runtime — slim image without compilers
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    APP_TARGET=ais \
    AIS_API_HOST=0.0.0.0 \
    AIS_API_PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

COPY . .
RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && useradd --create-home --shell /bin/bash ais \
    && chown -R ais:ais /app

USER ais

EXPOSE 8000 9001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /app/scripts/health_check.py

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
