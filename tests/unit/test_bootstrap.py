"""Tests for the bootstrap / config loading module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from aiswarm.bootstrap import (
    bootstrap_from_config,
    build_agents,
    build_loop_config,
    build_risk_engine,
    load_config,
    load_yaml,
    register_mandates,
    resolve_execution_mode,
)
from aiswarm.data.event_store import EventStore
from aiswarm.execution.aster_executor import ExecutionMode
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.loop.trading_loop import TradingLoop
from aiswarm.mandates.registry import MandateRegistry


def _make_config_dir() -> Path:
    """Create a temporary config directory with minimal YAML files."""
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
                        "mandate_id": "m1",
                        "strategy": "momentum_ma_crossover",
                        "symbols": ["BTCUSDT"],
                        "risk_budget": {
                            "max_capital": 5000.0,
                            "max_daily_loss": 0.02,
                            "max_drawdown": 0.05,
                            "max_open_orders": 2,
                            "max_position_notional": 2500.0,
                        },
                    }
                ],
                "session": {"default_duration_hours": 4},
                "staging": {"enabled": False},
            }
        )
    )
    (d / "execution.yaml").write_text(yaml.dump({"execution": {"allow_live": False}}))
    (d / "portfolio.yaml").write_text(yaml.dump({}))

    return d


class TestLoadYaml:
    def test_load_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump({"key": "value"}, f)
            f.flush()
            result = load_yaml(f.name)
        assert result == {"key": "value"}
        os.unlink(f.name)

    def test_load_nonexistent_file(self) -> None:
        result = load_yaml("/tmp/nonexistent_config_abc123.yaml")
        assert result == {}

    def test_load_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            result = load_yaml(f.name)
        assert result == {}
        os.unlink(f.name)


class TestLoadConfig:
    def test_merges_all_files(self) -> None:
        d = _make_config_dir()
        config = load_config(d)
        assert "risk" in config
        assert "mandates" in config
        assert "environment" in config

    def test_missing_files_handled(self) -> None:
        d = Path(tempfile.mkdtemp())
        config = load_config(d)
        assert isinstance(config, dict)


class TestBuildRiskEngine:
    def test_from_config(self) -> None:
        config = {
            "risk": {
                "max_position_weight": 0.10,
                "max_gross_exposure": 2.0,
                "max_daily_loss": 0.05,
                "max_leverage": 3.0,
            }
        }
        engine = build_risk_engine(config)
        assert engine.kill_switch.max_daily_loss == 0.05

    def test_defaults(self) -> None:
        engine = build_risk_engine({})
        assert engine.kill_switch.max_daily_loss == 0.02


class TestBuildLoopConfig:
    def test_from_config(self) -> None:
        config = {
            "symbols": ["BTCUSDT"],
            "loop": {"cycle_interval": 30.0},
        }
        lc = build_loop_config(config)
        assert lc.symbols == ("BTCUSDT",)
        assert lc.cycle_interval == 30.0

    def test_defaults(self) -> None:
        lc = build_loop_config({})
        assert lc.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")


class TestBuildAgents:
    def test_creates_default_agents(self) -> None:
        agents = build_agents({})
        assert len(agents) == 2
        ids = {a.agent_id for a in agents}
        assert "momentum_agent" in ids
        assert "funding_rate_agent" in ids


class TestRegisterMandates:
    def test_registers_from_config(self) -> None:
        es = EventStore(tempfile.mktemp(suffix=".db"))
        registry = MandateRegistry(es)
        config = {
            "mandates": [
                {
                    "mandate_id": "m1",
                    "strategy": "momentum",
                    "symbols": ["BTCUSDT"],
                    "risk_budget": {
                        "max_capital": 5000.0,
                        "max_daily_loss": 0.02,
                        "max_drawdown": 0.05,
                        "max_open_orders": 2,
                        "max_position_notional": 2500.0,
                    },
                }
            ]
        }
        register_mandates(registry, config)
        m = registry.get("m1")
        assert m is not None
        assert m.strategy == "momentum"
        assert m.risk_budget.max_capital == 5000.0

    def test_empty_mandates(self) -> None:
        es = EventStore(tempfile.mktemp(suffix=".db"))
        registry = MandateRegistry(es)
        register_mandates(registry, {})
        assert len(registry.list_all()) == 0


class TestResolveExecutionMode:
    def test_default_paper(self) -> None:
        os.environ.pop("AIS_EXECUTION_MODE", None)
        assert resolve_execution_mode({}) == ExecutionMode.PAPER

    def test_env_override(self) -> None:
        os.environ["AIS_EXECUTION_MODE"] = "live"
        try:
            assert resolve_execution_mode({}) == ExecutionMode.LIVE
        finally:
            os.environ.pop("AIS_EXECUTION_MODE")

    def test_config_mode(self) -> None:
        os.environ.pop("AIS_EXECUTION_MODE", None)
        assert resolve_execution_mode({"mode": "shadow"}) == ExecutionMode.SHADOW


class TestBootstrap:
    def test_bootstrap_creates_trading_loop(self) -> None:
        d = _make_config_dir()
        os.environ.pop("AIS_EXECUTION_MODE", None)
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret"
        try:
            gateway = MockMCPGateway()
            gateway.set_response(
                "mcp__aster__get_balance",
                {
                    "totalBalance": "100000.0",
                    "availableBalance": "100000.0",
                    "unrealizedProfit": "0.0",
                },
            )
            gateway.set_response("mcp__aster__get_positions", [])

            loop = bootstrap_from_config(
                config_dir=d,
                gateway=gateway,
                db_path=tempfile.mktemp(suffix=".db"),
            )
            assert isinstance(loop, TradingLoop)
            assert len(loop.agents) == 2
            assert loop.config.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_bootstrap_registers_mandates(self) -> None:
        d = _make_config_dir()
        os.environ.pop("AIS_EXECUTION_MODE", None)
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret"
        try:
            loop = bootstrap_from_config(
                config_dir=d,
                gateway=MockMCPGateway(),
                db_path=tempfile.mktemp(suffix=".db"),
            )
            # Coordinator should have mandate_validator wired
            assert loop.coordinator.mandate_validator is not None
        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)

    def test_bootstrap_shutdown_has_callbacks(self) -> None:
        d = _make_config_dir()
        os.environ.pop("AIS_EXECUTION_MODE", None)
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret"
        try:
            loop = bootstrap_from_config(
                config_dir=d,
                gateway=MockMCPGateway(),
                db_path=tempfile.mktemp(suffix=".db"),
            )
            # Should have at least 1 shutdown callback (cancel_all)
            assert len(loop.shutdown._callbacks) >= 1
        finally:
            os.environ.pop("AIS_RISK_HMAC_SECRET", None)
