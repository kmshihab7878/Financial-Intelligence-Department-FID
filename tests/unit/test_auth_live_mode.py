"""Tests for G-009: auth must require API key when AIS_EXECUTION_MODE=live."""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiswarm.api.auth import require_api_key


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint(
        key: str = pytest.importorskip("fastapi").Depends(require_api_key),
    ) -> dict[str, str]:
        return {"key": key}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestAuthLiveMode:
    def test_dev_mode_no_key_allows_access(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AIS_API_KEY", raising=False)
        monkeypatch.delenv("AIS_EXECUTION_MODE", raising=False)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json()["key"] == "dev"

    def test_live_mode_no_key_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AIS_API_KEY", raising=False)
        monkeypatch.setenv("AIS_EXECUTION_MODE", "live")
        resp = client.get("/test")
        assert resp.status_code == 503
        assert "live mode" in resp.json()["detail"].lower()

    def test_live_mode_with_key_requires_bearer(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AIS_API_KEY", "secure-test-key")
        monkeypatch.setenv("AIS_EXECUTION_MODE", "live")
        # Without bearer
        resp = client.get("/test")
        assert resp.status_code == 401
        # With valid bearer
        resp = client.get("/test", headers={"Authorization": "Bearer secure-test-key"})
        assert resp.status_code == 200

    def test_invalid_key_returns_403(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AIS_API_KEY", "real-key")
        resp = client.get("/test", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 403
