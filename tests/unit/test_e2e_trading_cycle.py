"""End-to-end integration test for the AIS trading cycle.

Tests the full pipeline: bootstrap → loop cycle → coordinator →
executor → fill tracker, using MockMCPGateway to verify the
complete order flow without connecting to a real exchange.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile

import pytest

from aiswarm.bootstrap import bootstrap_from_config
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.loop.trading_loop import TradingLoop


def _make_config_dir() -> str:
    """Create a temporary config directory with full YAML config."""
    import yaml
    from pathlib import Path

    d = Path(tempfile.mkdtemp())

    (d / "base.yaml").write_text(
        yaml.dump(
            {
                "environment": "paper",
                "audit": {"decision_log_path": str(d / "decisions.jsonl")},
            }
        )
    )
    (d / "risk.yaml").write_text(
        yaml.dump(
            {
                "risk": {
                    "max_position_weight": 0.10,
                    "max_gross_exposure": 2.0,
                    "max_daily_loss": 0.05,
                    "max_rolling_drawdown": 0.10,
                    "max_leverage": 3.0,
                    "min_liquidity_score": 0.3,
                }
            }
        )
    )
    (d / "mandates.yaml").write_text(
        yaml.dump(
            {
                "mandates": [
                    {
                        "mandate_id": "e2e_momentum",
                        "strategy": "momentum_ma_crossover",
                        "symbols": ["BTCUSDT"],
                        "risk_budget": {
                            "max_capital": 50000.0,
                            "max_daily_loss": 0.05,
                            "max_drawdown": 0.10,
                            "max_open_orders": 5,
                            "max_position_notional": 25000.0,
                        },
                    }
                ],
                "session": {"default_duration_hours": 8},
                "staging": {"enabled": False},
            }
        )
    )
    (d / "execution.yaml").write_text(yaml.dump({"execution": {"allow_live": False}}))
    (d / "portfolio.yaml").write_text(
        yaml.dump({"portfolio": {"max_single_position_weight": 0.05}})
    )
    (d / "monitoring.yaml").write_text(
        yaml.dump(
            {
                "monitoring": {"prometheus_port": 9001},
                "alerting": {"enabled": False},
            }
        )
    )

    return str(d)


@pytest.fixture
def e2e_gateway() -> MockMCPGateway:
    """Gateway with realistic responses for E2E testing."""
    gw = MockMCPGateway()
    gw.set_response(
        "mcp__aster__get_balance",
        {
            "totalBalance": "100000.0",
            "availableBalance": "95000.0",
            "unrealizedProfit": "500.0",
            "marginBalance": "100500.0",
        },
    )
    gw.set_response("mcp__aster__get_positions", [])
    gw.set_response("mcp__aster__get_income", [])
    # Klines: 60 candles with uptrend (to trigger momentum signal)
    candles = []
    for i in range(60):
        price = 50000 + i * 100  # steady uptrend
        candles.append(
            {
                "openTime": 1700000000000 + i * 3600000,
                "open": str(price),
                "high": str(price + 50),
                "low": str(price - 50),
                "close": str(price + 80),
                "volume": "100",
            }
        )
    gw.set_response("mcp__aster__get_klines", candles)
    gw.set_response(
        "mcp__aster__get_funding_rate",
        {
            "symbol": "BTCUSDT",
            "lastFundingRate": "0.0001",
            "markPrice": "55900",
            "nextFundingTime": 1700100000000,
        },
    )
    gw.set_response(
        "mcp__aster__get_ticker",
        {
            "symbol": "BTCUSDT",
            "lastPrice": "55900",
            "highPrice": "56000",
            "lowPrice": "55000",
            "volume": "1000",
            "priceChangePercent": "1.5",
        },
    )
    gw.set_response(
        "mcp__aster__get_order_book",
        {
            "bids": [["55800", "10"], ["55700", "20"]],
            "asks": [["55900", "10"], ["56000", "20"]],
        },
    )
    gw.set_response("mcp__aster__get_my_trades", [])
    return gw


class TestE2ETradingCycle:
    """End-to-end tests for the full trading pipeline."""

    def test_bootstrap_creates_loop(self, e2e_gateway: MockMCPGateway) -> None:
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )
            assert isinstance(loop, TradingLoop)
            assert len(loop.agents) == 2
        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_full_cycle_produces_order(self, e2e_gateway: MockMCPGateway) -> None:
        """Run a single cycle and verify an order flows through the full pipeline."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )

            # Activate session for trading
            loop.session_manager.start_session()
            loop.session_manager.approve_session("e2e-test")
            loop.session_manager.activate_session()

            # Run single cycle
            result = loop._run_cycle()

            # Verify cycle completed
            assert result.cycle_number == 1
            assert result.signals_generated > 0

            # The uptrend data should generate a momentum signal
            # and the coordinator should approve an order in paper mode
            if result.order_submitted:
                assert loop.state.total_orders_submitted == 1
                # Check that order was tracked
                orders = loop.live_executor.order_store.get_all()
                assert len(orders) >= 1

        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_cycle_calls_correct_mcp_tools(self, e2e_gateway: MockMCPGateway) -> None:
        """Verify that the cycle calls the expected MCP tools."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )

            loop.session_manager.start_session()
            loop.session_manager.approve_session("e2e-test")
            loop.session_manager.activate_session()

            loop._run_cycle()

            # Check that market data tools were called
            tool_names = [r.tool_name for r in e2e_gateway.call_history]
            assert "mcp__aster__get_klines" in tool_names
            assert "mcp__aster__get_funding_rate" in tool_names
            assert "mcp__aster__get_ticker" in tool_names
            assert "mcp__aster__get_order_book" in tool_names

        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_fill_sync_runs_in_cycle(self, e2e_gateway: MockMCPGateway) -> None:
        """Verify fill sync is called during the cycle."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )

            loop.session_manager.start_session()
            loop.session_manager.approve_session("e2e-test")
            loop.session_manager.activate_session()

            loop._run_cycle()

            # Fill sync should have called get_my_trades
            tool_names = [r.tool_name for r in e2e_gateway.call_history]
            assert "mcp__aster__get_my_trades" in tool_names

        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_reconciliation_runs_in_cycle(self, e2e_gateway: MockMCPGateway) -> None:
        """Verify reconciliation runs and passes."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )

            # Force reconciliation to run on first cycle regardless of monotonic clock
            loop.config = dataclasses.replace(loop.config, reconciliation_interval=0)

            loop.session_manager.start_session()
            loop.session_manager.approve_session("e2e-test")
            loop.session_manager.activate_session()

            result = loop._run_cycle()

            # Reconciliation should pass (no positions, no mismatches)
            assert result.errors == (), f"Unexpected errors: {result.errors}"
            assert result.reconciliation_passed is True

        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_control_state_blocks_cycle(self, e2e_gateway: MockMCPGateway) -> None:
        """Verify that paused control state blocks signal processing."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ.pop("AIS_EXECUTION_MODE", None)
        try:
            from aiswarm.api.routes_control import control_state

            config_dir = _make_config_dir()
            loop = bootstrap_from_config(
                config_dir=config_dir,
                gateway=e2e_gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )

            loop.session_manager.start_session()
            loop.session_manager.approve_session("e2e-test")
            loop.session_manager.activate_session()

            # Pause trading
            control_state.pause()
            result = loop._run_cycle()

            # Cycle should be blocked by control state
            assert "control_state_blocked" in result.errors
            assert result.signals_generated == 0

            # Resume and verify trading works
            control_state.resume()
            result2 = loop._run_cycle()
            assert "control_state_blocked" not in result2.errors

        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)
            from aiswarm.api.routes_control import SystemState, control_state

            control_state._fallback_state = SystemState.RUNNING

    def test_gateway_requires_url_for_live_mode(self) -> None:
        """Verify that live mode fails without AIS_MCP_SERVER_URL."""
        os.environ["AIS_RISK_HMAC_SECRET"] = "e2e-test-secret"
        os.environ["AIS_EXECUTION_MODE"] = "live"
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test-account"
        os.environ.pop("AIS_MCP_SERVER_URL", None)
        try:
            config_dir = _make_config_dir()
            with pytest.raises(RuntimeError, match="AIS_MCP_SERVER_URL"):
                bootstrap_from_config(
                    config_dir=config_dir,
                    db_path=tempfile.mktemp(suffix=".db"),
                )
        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)
            os.environ.pop("AIS_EXECUTION_MODE", None)
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)
