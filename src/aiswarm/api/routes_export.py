"""Export API routes — portfolio tracking and tax exports.

Provides endpoints for triggering portfolio snapshot exports and
tax report generation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aiswarm.api.auth import require_api_key
from aiswarm.api.rate_limit import require_general_rate_limit
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/export", tags=["export"])


class TaxExportRequest(BaseModel):
    format: str = "csv"  # csv, koinly, cointracker
    limit: int = Field(default=10000, ge=1, le=100000)


@router.post("/tax", dependencies=[Depends(require_general_rate_limit)])
def export_tax(
    req: TaxExportRequest,
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Export trade history in tax-compatible format.

    Returns the CSV content as a string in the response.
    """
    from aiswarm.integrations.tax.exporter import TaxExporter, TaxFormat

    # Lazy import to avoid circular deps at module load
    try:
        from aiswarm.data.event_store import EventStore

        event_store = EventStore()
    except Exception as e:
        logger.error("EventStore unavailable for export", extra={"extra_json": {"error": str(e)}})
        return {"success": False, "error": "EventStore unavailable"}

    try:
        tax_format = TaxFormat(req.format)
    except ValueError:
        return {
            "success": False,
            "error": f"Unknown format: {req.format}. Use: csv, koinly, cointracker",
        }

    exporter = TaxExporter(event_store)
    result = exporter.export(tax_format=tax_format, limit=req.limit)

    return {
        "success": result.success,
        "format": result.format,
        "rows": result.rows,
        "content": result.content,
        "message": result.message,
    }
