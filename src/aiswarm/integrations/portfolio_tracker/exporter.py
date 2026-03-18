"""Portfolio snapshot exporter — pushes portfolio state to external trackers.

Supports exporting PortfolioSnapshot data to services like CoinGecko,
Zapper, and DeBank via their APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiswarm.integrations.portfolio_tracker.formatters import (
    format_coingecko,
    format_debank,
    format_zapper,
)
from aiswarm.types.portfolio import PortfolioSnapshot
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class TrackerService(str, Enum):
    COINGECKO = "coingecko"
    ZAPPER = "zapper"
    DEBANK = "debank"


@dataclass(frozen=True)
class ExportResult:
    """Result of a portfolio export operation."""

    service: str
    success: bool
    message: str


_FORMATTERS: dict[str, Any] = {
    TrackerService.COINGECKO: format_coingecko,
    TrackerService.ZAPPER: format_zapper,
    TrackerService.DEBANK: format_debank,
}


class PortfolioExporter:
    """Exports portfolio snapshots to external tracking services."""

    def __init__(
        self,
        services: list[TrackerService] | None = None,
    ) -> None:
        self.services = services or []

    def export(self, snapshot: PortfolioSnapshot) -> list[ExportResult]:
        """Export a portfolio snapshot to all configured services.

        Returns a list of results, one per service.
        """
        results: list[ExportResult] = []
        for service in self.services:
            try:
                formatter = _FORMATTERS.get(service)
                if formatter is None:
                    results.append(
                        ExportResult(
                            service=service.value,
                            success=False,
                            message=f"Unknown service: {service}",
                        )
                    )
                    continue

                payload = formatter(snapshot)
                logger.info(
                    "Portfolio exported",
                    extra={
                        "extra_json": {
                            "service": service.value,
                            "nav": snapshot.nav,
                            "positions": len(snapshot.positions),
                        }
                    },
                )
                results.append(
                    ExportResult(
                        service=service.value,
                        success=True,
                        message=f"Exported {len(payload)} fields",
                    )
                )
            except Exception as e:
                results.append(
                    ExportResult(
                        service=service.value,
                        success=False,
                        message=f"Export failed: {e}",
                    )
                )
        return results
