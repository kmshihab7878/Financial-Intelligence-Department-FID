"""Tests for the loop configuration."""

from __future__ import annotations

from aiswarm.loop.config import LoopConfig


class TestLoopConfig:
    def test_defaults(self) -> None:
        config = LoopConfig()
        assert config.cycle_interval == 60.0
        assert config.portfolio_sync_interval == 30.0
        assert config.fill_sync_interval == 15.0
        assert config.reconciliation_interval == 60.0
        assert config.klines_interval == "1h"
        assert config.klines_limit == 100
        assert config.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        assert config.default_leverage == 1
        assert config.default_margin_mode == "ISOLATED"
        assert config.max_consecutive_errors == 5
        assert config.heartbeat_interval == 10.0

    def test_custom_config(self) -> None:
        config = LoopConfig(
            cycle_interval=30.0,
            symbols=("BTCUSDT",),
            default_leverage=2,
            max_consecutive_errors=3,
        )
        assert config.cycle_interval == 30.0
        assert config.symbols == ("BTCUSDT",)
        assert config.default_leverage == 2
        assert config.max_consecutive_errors == 3

    def test_frozen(self) -> None:
        config = LoopConfig()
        try:
            config.cycle_interval = 10.0  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass
