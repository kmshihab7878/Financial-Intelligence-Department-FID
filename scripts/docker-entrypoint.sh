#!/bin/bash
# AIS Docker Entrypoint Script

set -e

APP_TARGET="${APP_TARGET:-ais}"

if [ "$APP_TARGET" = "ais" ]; then
    HOST="${AIS_API_HOST:-0.0.0.0}"
    PORT="${AIS_API_PORT:-8000}"
    echo "Starting AIS API on $HOST:$PORT"
    exec uvicorn aiswarm.api.app:app --host "$HOST" --port "$PORT"
fi

if [ "$APP_TARGET" = "ais-loop" ]; then
    echo "Starting AIS trading loop (mode=${AIS_EXECUTION_MODE:-paper})"
    exec python -m aiswarm --config /app/config/ ${AIS_LOOP_ARGS:-}
fi

echo "ERROR: Unknown APP_TARGET='$APP_TARGET'. Expected 'ais' or 'ais-loop'."
exit 1
