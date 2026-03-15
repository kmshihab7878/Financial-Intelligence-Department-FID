"""Alert dispatcher — sends webhook notifications for critical events.

G-003: Replaces the 2-line stub with a real AlertDispatcher that posts
JSON payloads to a configurable webhook URL.

Severity filter: only dispatches alerts at or above the configured level.
Graceful failure: network errors are logged but never crash the loop.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

import httpx

from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


class AlertSeverity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


SEVERITY_MAP: dict[str, AlertSeverity] = {
    "info": AlertSeverity.INFO,
    "warning": AlertSeverity.WARNING,
    "error": AlertSeverity.ERROR,
    "critical": AlertSeverity.CRITICAL,
}


class AlertDispatcher:
    """Dispatches alerts to a webhook endpoint."""

    def __init__(
        self,
        webhook_url: str = "",
        severity_filter: str = "warning",
        enabled: bool = True,
        timeout: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.min_severity = SEVERITY_MAP.get(severity_filter.lower(), AlertSeverity.WARNING)
        self.enabled = enabled and bool(webhook_url)
        self.timeout = timeout

    def send(
        self,
        message: str,
        severity: str = "warning",
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert if it meets the severity threshold.

        Returns True if the alert was dispatched (or filtered), False on error.
        Never raises — failures are logged.
        """
        sev = SEVERITY_MAP.get(severity.lower(), AlertSeverity.WARNING)
        if sev < self.min_severity:
            return True

        payload = {
            "severity": severity,
            "message": message,
            "timestamp": utc_now().isoformat(),
            "context": context or {},
        }

        if not self.enabled:
            logger.info(
                "Alert (not dispatched — disabled)",
                extra={"extra_json": payload},
            )
            return True

        try:
            resp = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info(
                "Alert dispatched",
                extra={"extra_json": {"severity": severity, "status": resp.status_code}},
            )
            return True
        except Exception as e:
            logger.error(
                "Alert dispatch failed",
                extra={"extra_json": {"error": str(e), "message": message}},
            )
            return False


def build_alert(message: str) -> dict[str, str]:
    """Legacy helper — builds a simple alert dict."""
    return {"severity": "warning", "message": message}
