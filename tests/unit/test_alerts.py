"""Tests for G-003: AlertDispatcher webhook alerting."""

from __future__ import annotations


from aiswarm.monitoring.alerts import (
    AlertDispatcher,
    AlertSeverity,
    build_alert,
)


class TestAlertDispatcher:
    def test_disabled_dispatcher_logs_only(self) -> None:
        dispatcher = AlertDispatcher(webhook_url="", enabled=False)
        assert dispatcher.enabled is False
        result = dispatcher.send("test message", severity="critical")
        assert result is True  # Not dispatched, but not an error

    def test_severity_filter_blocks_low_severity(self) -> None:
        dispatcher = AlertDispatcher(
            webhook_url="http://example.com/hook",
            severity_filter="error",
            enabled=True,
        )
        # Warning is below error filter — should be filtered out
        result = dispatcher.send("low severity", severity="warning")
        assert result is True

    def test_severity_filter_passes_high_severity(self) -> None:
        """Critical is above warning filter — but we can't actually POST.
        We test that the dispatch is attempted (returns False on connection error)."""
        dispatcher = AlertDispatcher(
            webhook_url="http://127.0.0.1:1/nonexistent",
            severity_filter="warning",
            enabled=True,
            timeout=0.5,
        )
        result = dispatcher.send("critical alert", severity="critical")
        # Will fail to connect — but should NOT raise
        assert result is False

    def test_severity_ordering(self) -> None:
        assert AlertSeverity.INFO < AlertSeverity.WARNING
        assert AlertSeverity.WARNING < AlertSeverity.ERROR
        assert AlertSeverity.ERROR < AlertSeverity.CRITICAL

    def test_build_alert_legacy(self) -> None:
        alert = build_alert("test")
        assert alert["severity"] == "warning"
        assert alert["message"] == "test"

    def test_disabled_when_no_url(self) -> None:
        dispatcher = AlertDispatcher(webhook_url="", enabled=True)
        assert dispatcher.enabled is False

    def test_send_with_context(self) -> None:
        dispatcher = AlertDispatcher(webhook_url="", enabled=False)
        result = dispatcher.send(
            "test",
            severity="error",
            context={"cycle": 42, "reason": "drawdown"},
        )
        assert result is True
