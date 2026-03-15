"""Daily review report models.

Generated at the end of each trading session to provide a comprehensive
summary for operator review before the next session is approved.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MandateSummary(BaseModel):
    """Per-mandate summary within a daily review."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str
    strategy: str
    fills: int = Field(default=0, ge=0)
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    peak_exposure: float = 0.0
    max_drawdown: float = 0.0
    slippage_bps: float = 0.0


class DailyReviewReport(BaseModel):
    """End-of-session review report for operator sign-off."""

    model_config = ConfigDict(frozen=True)

    report_id: str
    session_id: str
    generated_at: datetime
    session_start: datetime
    session_end: datetime
    mandate_summaries: tuple[MandateSummary, ...]
    total_fills: int = Field(default=0, ge=0)
    total_pnl: float = 0.0
    reconciliation_passed: bool = True
    reconciliation_mismatches: int = Field(default=0, ge=0)
    risk_events_count: int = Field(default=0, ge=0)
    notes: str = ""
