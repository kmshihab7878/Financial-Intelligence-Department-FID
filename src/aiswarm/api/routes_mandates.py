"""Mandate CRUD API routes.

Provides endpoints for creating, listing, pausing, and revoking mandates.
All endpoints require Bearer token authentication.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aiswarm.api.auth import require_api_key
from aiswarm.mandates.models import MandateRiskBudget, MandateStatus
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)
router = APIRouter()

# Module-level registry — injected at app startup
_registry: MandateRegistry | None = None


def set_registry(registry: MandateRegistry) -> None:
    global _registry
    _registry = registry


def _get_registry() -> MandateRegistry:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Mandate registry not configured")
    return _registry


# --- Request models ---


class CreateMandateRequest(BaseModel):
    mandate_id: str
    strategy: str
    symbols: list[str]
    max_capital: float
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.05
    max_position_notional: float = 0.0


# --- Endpoints ---


@router.post("/mandates/")
def create_mandate(
    req: CreateMandateRequest,
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Create a new mandate."""
    registry = _get_registry()

    risk_budget = MandateRiskBudget(
        max_capital=req.max_capital,
        max_daily_loss=req.max_daily_loss,
        max_drawdown=req.max_drawdown,
        max_position_notional=req.max_position_notional,
    )

    mandate = registry.create(
        mandate_id=req.mandate_id,
        strategy=req.strategy,
        symbols=tuple(req.symbols),
        risk_budget=risk_budget,
    )

    logger.info(
        "Mandate created via API",
        extra={"extra_json": {"mandate_id": mandate.mandate_id}},
    )
    return {
        "action": "created",
        "mandate": mandate.model_dump(mode="json"),
        "timestamp": utc_now().isoformat(),
    }


@router.get("/mandates/")
def list_mandates(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """List all mandates."""
    registry = _get_registry()
    mandates = registry.list_all()
    return {
        "mandates": [m.model_dump(mode="json") for m in mandates],
        "count": len(mandates),
        "timestamp": utc_now().isoformat(),
    }


@router.get("/mandates/{mandate_id}")
def get_mandate(mandate_id: str, _: str = Depends(require_api_key)) -> dict[str, Any]:
    """Get a specific mandate by ID."""
    registry = _get_registry()
    mandate = registry.get(mandate_id)
    if mandate is None:
        raise HTTPException(status_code=404, detail=f"Mandate {mandate_id} not found")
    return {
        "mandate": mandate.model_dump(mode="json"),
        "timestamp": utc_now().isoformat(),
    }


@router.post("/mandates/{mandate_id}/pause")
def pause_mandate(mandate_id: str, _: str = Depends(require_api_key)) -> dict[str, Any]:
    """Pause a mandate (stop matching new orders to it)."""
    registry = _get_registry()
    mandate = registry.get(mandate_id)
    if mandate is None:
        raise HTTPException(status_code=404, detail=f"Mandate {mandate_id} not found")

    registry.update_status(mandate_id, MandateStatus.PAUSED)
    logger.warning(
        "Mandate paused via API",
        extra={"extra_json": {"mandate_id": mandate_id}},
    )
    return {
        "action": "paused",
        "mandate_id": mandate_id,
        "timestamp": utc_now().isoformat(),
    }


@router.post("/mandates/{mandate_id}/revoke")
def revoke_mandate(mandate_id: str, _: str = Depends(require_api_key)) -> dict[str, Any]:
    """Permanently revoke a mandate."""
    registry = _get_registry()
    mandate = registry.get(mandate_id)
    if mandate is None:
        raise HTTPException(status_code=404, detail=f"Mandate {mandate_id} not found")

    registry.revoke(mandate_id)
    logger.warning(
        "Mandate revoked via API",
        extra={"extra_json": {"mandate_id": mandate_id}},
    )
    return {
        "action": "revoked",
        "mandate_id": mandate_id,
        "timestamp": utc_now().isoformat(),
    }
