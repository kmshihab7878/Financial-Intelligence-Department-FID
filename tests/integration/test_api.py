"""Integration tests for the FastAPI control plane.

Tests the API endpoints with the real FastAPI app, verifying
authentication, health checks, and control operations.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from aiswarm.api.app import app


@pytest.fixture()
def api_key() -> str:
    key = "test-integration-api-key"
    os.environ["AIS_API_KEY"] = key
    return key


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


class TestHealthEndpoints:
    """Test public health and metrics endpoints."""

    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_metrics_returns_200(self, client: TestClient) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_openapi_schema_available(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Autonomous Investment Swarm"
        assert "paths" in schema

    def test_swagger_ui_available(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_available(self, client: TestClient) -> None:
        response = client.get("/redoc")
        assert response.status_code == 200


class TestAuthentication:
    """Test API authentication enforcement."""

    def test_control_endpoint_requires_auth(self, client: TestClient) -> None:
        response = client.get("/control/status")
        assert response.status_code in (401, 403)

    def test_control_endpoint_with_valid_auth(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        response = client.get("/control/status", headers=auth_headers)
        assert response.status_code == 200

    def test_control_endpoint_with_invalid_auth(self, client: TestClient) -> None:
        headers = {"Authorization": "Bearer wrong-key"}
        response = client.get("/control/status", headers=headers)
        assert response.status_code in (401, 403)


class TestControlEndpoints:
    """Test control plane operations."""

    def test_get_mode(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        response = client.get("/control/mode", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "default_mode" in data
