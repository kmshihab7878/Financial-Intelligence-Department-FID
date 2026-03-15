"""Tests for the control API endpoints."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from aiswarm.api.app import app
from aiswarm.api.routes_control import SystemState, control_state


class TestControlAPI:
    def setup_method(self) -> None:
        os.environ["AIS_API_KEY"] = "test-api-key"
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-api-key"}
        # Reset fallback state between tests (Redis may not be available)
        control_state._fallback_state = SystemState.RUNNING
        control_state._fallback_paused_at = None
        control_state._fallback_kill_reason = None

    def test_get_status(self) -> None:
        resp = self.client.get("/control/status", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "running"
        assert data["is_trading_allowed"] is True

    def test_get_mode(self) -> None:
        resp = self.client.get("/control/mode", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["default_mode"] == "paper"

    def test_pause_and_resume(self) -> None:
        resp = self.client.post(
            "/control/pause",
            headers=self.headers,
            json={"reason": "test pause"},
        )
        assert resp.status_code == 200
        assert resp.json()["action"] == "paused"
        assert control_state.state == SystemState.PAUSED

        resp = self.client.post("/control/resume", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["action"] == "resumed"
        assert control_state.state == SystemState.RUNNING

    def test_kill_switch(self) -> None:
        resp = self.client.post(
            "/control/kill-switch",
            headers=self.headers,
            json={"reason": "emergency"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "killed"
        assert "cancel_instructions" in data
        assert control_state.state == SystemState.KILLED

    def test_resume_refused_after_kill(self) -> None:
        control_state.kill("test")
        resp = self.client.post("/control/resume", headers=self.headers)
        assert resp.status_code == 200
        assert resp.json()["action"] == "refused"
        assert control_state.state == SystemState.KILLED

    def test_cancel_all(self) -> None:
        resp = self.client.post(
            "/control/cancel-all",
            headers=self.headers,
            json={"symbols": ["BTCUSDT"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "cancel_all_prepared"
        assert "cancel_instructions" in data

    def test_deleverage(self) -> None:
        resp = self.client.post(
            "/control/deleverage",
            headers=self.headers,
            json={"symbol": "BTCUSDT", "reduce_pct": 0.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "deleverage_prepared"
        assert data["reduce_pct"] == 0.5

    def test_unauthenticated_request_rejected(self) -> None:
        resp = self.client.get("/control/status")
        assert resp.status_code == 401
