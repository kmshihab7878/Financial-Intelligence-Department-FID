"""Tests for the TradingView webhook integration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from aiswarm.integrations.tradingview.auth import validate_webhook_passphrase
from aiswarm.integrations.tradingview.models import TVAlertPayload
from aiswarm.integrations.tradingview.webhook import (
    _action_to_direction,
    _tv_to_signal,
    drain_signals,
    pending_count,
)


@pytest.fixture(autouse=True)
def _env() -> None:
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret"


class TestTVAlertPayload:
    def test_valid_payload(self) -> None:
        p = TVAlertPayload(symbol="BTCUSDT", action="buy")
        assert p.symbol == "BTCUSDT"
        assert p.action == "buy"
        assert p.confidence == 0.7
        assert p.strategy == "tradingview"

    def test_full_payload(self) -> None:
        p = TVAlertPayload(
            symbol="ETHUSDT",
            action="sell",
            strategy="my_strategy",
            confidence=0.9,
            price=3000.0,
            thesis="ETH bearish divergence on RSI",
            timeframe="4h",
            exchange="binance",
            passphrase="secret123",
        )
        assert p.symbol == "ETHUSDT"
        assert p.action == "sell"
        assert p.confidence == 0.9
        assert p.price == 3000.0


class TestActionToDirection:
    def test_buy(self) -> None:
        assert _action_to_direction("buy") == 1
        assert _action_to_direction("BUY") == 1
        assert _action_to_direction("long") == 1

    def test_sell(self) -> None:
        assert _action_to_direction("sell") == -1
        assert _action_to_direction("SELL") == -1
        assert _action_to_direction("short") == -1

    def test_flat(self) -> None:
        assert _action_to_direction("flat") == 0
        assert _action_to_direction("close") == 0


class TestTVToSignal:
    def test_buy_signal(self) -> None:
        payload = TVAlertPayload(
            symbol="BTCUSDT",
            action="buy",
            confidence=0.85,
            price=50000.0,
            thesis="BTC breakout above resistance",
        )
        signal = _tv_to_signal(payload)

        assert signal.symbol == "BTCUSDT"
        assert signal.direction == 1
        assert signal.confidence == 0.85
        assert signal.agent_id == "tradingview_webhook"
        assert signal.reference_price == 50000.0
        assert signal.signal_id.startswith("tv_")

    def test_sell_signal(self) -> None:
        payload = TVAlertPayload(
            symbol="ETHUSDT",
            action="sell",
            thesis="ETH bearish signal from TV",
        )
        signal = _tv_to_signal(payload)

        assert signal.direction == -1
        assert signal.expected_return < 0

    def test_timeframe_mapping(self) -> None:
        payload = TVAlertPayload(
            symbol="BTCUSDT",
            action="buy",
            timeframe="4h",
            thesis="Four hour timeframe signal",
        )
        signal = _tv_to_signal(payload)
        assert signal.horizon_minutes == 240


class TestWebhookAuth:
    def test_valid_passphrase(self) -> None:
        with patch("aiswarm.integrations.tradingview.auth.get_secrets_provider") as mock:
            mock.return_value.get_secret.return_value = "correct_secret"
            assert validate_webhook_passphrase("correct_secret") is True

    def test_invalid_passphrase(self) -> None:
        with patch("aiswarm.integrations.tradingview.auth.get_secrets_provider") as mock:
            mock.return_value.get_secret.return_value = "correct_secret"
            assert validate_webhook_passphrase("wrong_secret") is False

    def test_no_secret_configured(self) -> None:
        with patch("aiswarm.integrations.tradingview.auth.get_secrets_provider") as mock:
            mock.return_value.get_secret.return_value = ""
            assert validate_webhook_passphrase("anything") is False


class TestSignalQueue:
    def test_drain_empty(self) -> None:
        drain_signals()  # Clear any existing
        assert drain_signals() == []
        assert pending_count() == 0

    def test_drain_returns_and_clears(self) -> None:
        from aiswarm.integrations.tradingview.webhook import _signal_queue

        drain_signals()  # Clear
        payload = TVAlertPayload(symbol="BTCUSDT", action="buy", thesis="Test signal for queue")
        signal = _tv_to_signal(payload)
        _signal_queue.append(signal)

        assert pending_count() == 1
        drained = drain_signals()
        assert len(drained) == 1
        assert drained[0].symbol == "BTCUSDT"
        assert pending_count() == 0
