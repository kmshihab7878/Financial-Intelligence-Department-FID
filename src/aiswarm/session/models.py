"""Trading session models.

A TradingSession represents a bounded trading window. The system only
processes signals when a session is ACTIVE. Sessions follow a strict
lifecycle: PENDING_REVIEW -> APPROVED -> ACTIVE -> ENDED -> PENDING_REVIEW.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SessionState(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVE = "active"
    ENDED = "ended"


class TradingSession(BaseModel):
    """A bounded trading session with operator approval gate."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    state: SessionState = SessionState.PENDING_REVIEW
    scheduled_start: datetime
    scheduled_end: datetime
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    approved_by: str | None = None
    approval_notes: str = ""
    created_at: datetime
    total_fills: int = Field(default=0, ge=0)
    total_pnl: float = 0.0
