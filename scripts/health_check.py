#!/usr/bin/env python3
"""Health checks for AIS runtimes."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests


@dataclass(frozen=True)
class ServiceCheck:
    name: str
    url: str


def _timeout_seconds() -> float:
    return float(os.getenv("HEALTHCHECK_TIMEOUT", "10"))


def _profile() -> str:
    profile = os.getenv("STACK_PROFILE", "").strip().lower()
    if profile:
        return profile
    target = os.getenv("APP_TARGET", "ais").strip().lower()
    if target == "ais-loop":
        return "ais-loop"
    return "ais"


def _service_checks(profile: str) -> list[ServiceCheck]:
    ais_checks = [
        ServiceCheck("AIS API", os.getenv("AIS_API_URL", "http://localhost:8000/health")),
    ]
    if profile in ("ais", "ais-api"):
        return ais_checks
    if profile == "ais-loop":
        return []  # Loop uses heartbeat file check
    raise ValueError(f"Unsupported STACK_PROFILE: {profile}")


def check_endpoint(check: ServiceCheck) -> bool:
    """Return True when the configured endpoint answers with a 2xx response."""
    try:
        response = requests.get(check.url, timeout=_timeout_seconds())
        if response.ok:
            print(f"[ok] {check.name}: {check.url}")
            return True
        print(f"[fail] {check.name}: status={response.status_code} url={check.url}")
        return False
    except requests.RequestException as exc:
        print(f"[fail] {check.name}: {exc} url={check.url}")
        return False


def check_loop_heartbeat(max_age: float = 120.0) -> bool:
    """Check that the trading loop heartbeat file is recent."""
    hb_path = Path("/tmp/ais_loop_heartbeat")
    if not hb_path.exists():
        print("[fail] Loop heartbeat: file missing")
        return False
    try:
        ts = float(hb_path.read_text().strip())
        age = time.time() - ts
        if age < max_age:
            print(f"[ok] Loop heartbeat: {age:.0f}s ago")
            return True
        print(f"[fail] Loop heartbeat: stale ({age:.0f}s ago)")
        return False
    except (ValueError, OSError) as e:
        print(f"[fail] Loop heartbeat: {e}")
        return False


def check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        import redis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(url, socket_timeout=2, decode_responses=True)
        client.ping()
        print("[ok] Redis: connected")
        return True
    except Exception as e:
        print(f"[fail] Redis: {e}")
        return False


def main() -> None:
    """Run the configured health checks and exit non-zero on failure."""
    profile = _profile()
    print(f"Health check profile={profile} time={datetime.now().isoformat()}")
    print("-" * 60)

    all_healthy = True

    for check in _service_checks(profile):
        all_healthy = check_endpoint(check) and all_healthy

    # Additional checks for AIS profiles
    if profile in ("ais", "ais-api", "ais-loop"):
        all_healthy = check_redis() and all_healthy

    if profile == "ais-loop":
        all_healthy = check_loop_heartbeat() and all_healthy

    print("-" * 60)
    sys.exit(0 if all_healthy else 1)


if __name__ == "__main__":
    main()
