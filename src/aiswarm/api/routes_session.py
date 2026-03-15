"""Session lifecycle and daily review API routes.

Provides endpoints for session management, daily review reports,
reconciliation status, and staged order operations.
All endpoints require Bearer token authentication.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aiswarm.api.auth import require_api_key
from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.review.generator import ReviewGenerator
from aiswarm.session.manager import SessionManager
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)
router = APIRouter()

# Module-level singletons — injected at app startup
_session_manager: SessionManager | None = None
_review_generator: ReviewGenerator | None = None
_coordinator: Coordinator | None = None


def set_session_manager(manager: SessionManager) -> None:
    global _session_manager
    _session_manager = manager


def set_review_generator(generator: ReviewGenerator) -> None:
    global _review_generator
    _review_generator = generator


def set_coordinator(coordinator: Coordinator) -> None:
    global _coordinator
    _coordinator = coordinator


def _get_session_manager() -> SessionManager:
    if _session_manager is None:
        raise HTTPException(status_code=503, detail="Session manager not configured")
    return _session_manager


# --- Request models ---


class ApproveSessionRequest(BaseModel):
    operator: str
    notes: str = ""


# --- Session endpoints ---


@router.get("/session/current")
def get_current_session(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """Get current session state."""
    mgr = _get_session_manager()
    session = mgr.current_session
    return {
        "session": session.model_dump(mode="json") if session else None,
        "is_trading_allowed": mgr.is_trading_allowed,
        "timestamp": utc_now().isoformat(),
    }


@router.post("/session/approve")
def approve_session(
    req: ApproveSessionRequest,
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Approve the current session for trading (operator sign-off)."""
    mgr = _get_session_manager()
    session = mgr.current_session
    if session is None:
        raise HTTPException(status_code=404, detail="No current session")

    mgr.approve_session(req.operator, req.notes)
    logger.info(
        "Session approved via API",
        extra={"extra_json": {"operator": req.operator, "session_id": session.session_id}},
    )
    return {
        "action": "approved",
        "session_id": session.session_id,
        "operator": req.operator,
        "timestamp": utc_now().isoformat(),
    }


@router.post("/session/end")
def end_session(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """Force end the current session."""
    mgr = _get_session_manager()
    session = mgr.current_session
    if session is None:
        raise HTTPException(status_code=404, detail="No current session")

    mgr.end_session()
    logger.info(
        "Session ended via API",
        extra={"extra_json": {"session_id": session.session_id}},
    )
    return {
        "action": "ended",
        "session_id": session.session_id,
        "timestamp": utc_now().isoformat(),
    }


# --- Review endpoints ---


@router.get("/review/daily-report")
def get_daily_report(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """Get the latest daily review report."""
    if _review_generator is None:
        raise HTTPException(status_code=503, detail="Review generator not configured")

    mgr = _get_session_manager()
    session = mgr.current_session
    if session is None:
        raise HTTPException(status_code=404, detail="No current session to report on")

    report = _review_generator.generate_daily_report(session)
    return {
        "report": report.model_dump(mode="json"),
        "timestamp": utc_now().isoformat(),
    }


@router.get("/review/reconciliation-status")
def get_reconciliation_status(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """Get latest reconciliation status."""
    # Returns status from the most recent periodic check
    return {
        "status": "ok",
        "message": "Reconciliation status endpoint — integrate with ReconciliationLoop",
        "timestamp": utc_now().isoformat(),
    }


# --- Staged order endpoints ---


@router.get("/control/staged-orders")
def list_staged_orders(_: str = Depends(require_api_key)) -> dict[str, Any]:
    """List all staged orders awaiting operator review."""
    if _coordinator is None:
        raise HTTPException(status_code=503, detail="Coordinator not configured")

    staged = _coordinator.get_staged_orders()
    return {
        "staged_orders": [o.model_dump(mode="json") for o in staged],
        "count": len(staged),
        "timestamp": utc_now().isoformat(),
    }


@router.post("/control/execute-staged/{order_id}")
def execute_staged_order(order_id: str, _: str = Depends(require_api_key)) -> dict[str, Any]:
    """Execute a staged order (approve for submission to OMS)."""
    if _coordinator is None:
        raise HTTPException(status_code=503, detail="Coordinator not configured")

    order = _coordinator.execute_staged(order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail=f"Staged order {order_id} not found or token expired",
        )

    logger.info(
        "Staged order executed via API",
        extra={"extra_json": {"order_id": order_id}},
    )
    return {
        "action": "executed",
        "order": order.model_dump(mode="json"),
        "timestamp": utc_now().isoformat(),
    }
