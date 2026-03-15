"""Mandate models for constrained live trading.

A Mandate defines the authorized scope for a trading strategy:
which symbols it may trade, its capital budget, and its risk limits.
No order executes without matching an active mandate.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MandateStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    EXPIRED = "expired"


class MandateRiskBudget(BaseModel):
    """Per-mandate risk budget — layered on top of global limits."""

    model_config = ConfigDict(frozen=True)

    max_capital: float = Field(gt=0, description="Max notional capital for this mandate")
    max_daily_loss: float = Field(
        gt=0, le=1.0, description="Max daily loss as fraction of mandate capital"
    )
    max_drawdown: float = Field(
        gt=0, le=1.0, description="Max drawdown as fraction of mandate capital"
    )
    max_open_orders: int = Field(default=5, gt=0, description="Max concurrent open orders")
    max_position_notional: float = Field(
        default=0.0, ge=0, description="Max notional per position (0 = use max_capital)"
    )

    @property
    def effective_position_notional(self) -> float:
        return self.max_position_notional if self.max_position_notional > 0 else self.max_capital


class Mandate(BaseModel):
    """Trading mandate — defines what a strategy is allowed to do."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str
    strategy: str
    symbols: tuple[str, ...]
    risk_budget: MandateRiskBudget
    status: MandateStatus = MandateStatus.ACTIVE
    created_at: datetime
    updated_at: datetime | None = None
    created_by: str = "system"
    notes: str = ""
