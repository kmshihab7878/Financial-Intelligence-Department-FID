"""Tax export — exports trade history from EventStore to tax-compatible formats.

Supports CSV, Koinly, and CoinTracker export formats.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiswarm.data.event_store import EventStore
from aiswarm.integrations.tax.formatters import (
    format_cointracker_row,
    format_csv_row,
    format_koinly_row,
)
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class TaxFormat(str, Enum):
    CSV = "csv"
    KOINLY = "koinly"
    COINTRACKER = "cointracker"


@dataclass(frozen=True)
class TaxExportResult:
    """Result of a tax export operation."""

    format: str
    rows: int
    content: str
    success: bool
    message: str


# CSV headers per format
_HEADERS: dict[TaxFormat, list[str]] = {
    TaxFormat.CSV: [
        "date",
        "type",
        "symbol",
        "side",
        "quantity",
        "price",
        "total",
        "fee",
        "fee_currency",
        "pnl",
    ],
    TaxFormat.KOINLY: [
        "Date",
        "Sent Amount",
        "Sent Currency",
        "Received Amount",
        "Received Currency",
        "Fee Amount",
        "Fee Currency",
        "Net Worth Amount",
        "Net Worth Currency",
        "Label",
        "Description",
        "TxHash",
    ],
    TaxFormat.COINTRACKER: [
        "Date",
        "Type",
        "Received Quantity",
        "Received Currency",
        "Sent Quantity",
        "Sent Currency",
        "Fee Amount",
        "Fee Currency",
    ],
}

_ROW_FORMATTERS: dict[TaxFormat, Any] = {
    TaxFormat.CSV: format_csv_row,
    TaxFormat.KOINLY: format_koinly_row,
    TaxFormat.COINTRACKER: format_cointracker_row,
}


class TaxExporter:
    """Exports trade history from EventStore to tax-compatible formats."""

    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store

    def export(
        self,
        tax_format: TaxFormat = TaxFormat.CSV,
        limit: int = 10000,
    ) -> TaxExportResult:
        """Export trades to the specified format.

        Reads fill events from EventStore and formats them.
        """
        try:
            events = self.event_store.get_events(event_type="order_filled", limit=limit)

            headers = _HEADERS.get(tax_format, _HEADERS[TaxFormat.CSV])
            formatter = _ROW_FORMATTERS.get(tax_format, format_csv_row)

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)

            for event in events:
                payload = event.get("payload", {})
                row = formatter(event.get("timestamp", ""), payload)
                writer.writerow(row)

            content = output.getvalue()
            logger.info(
                "Tax export completed",
                extra={
                    "extra_json": {
                        "format": tax_format.value,
                        "rows": len(events),
                    }
                },
            )

            return TaxExportResult(
                format=tax_format.value,
                rows=len(events),
                content=content,
                success=True,
                message=f"Exported {len(events)} trades",
            )

        except Exception as e:
            logger.error(
                "Tax export failed",
                extra={"extra_json": {"format": tax_format.value, "error": str(e)}},
            )
            return TaxExportResult(
                format=tax_format.value,
                rows=0,
                content="",
                success=False,
                message=f"Export failed: {e}",
            )
