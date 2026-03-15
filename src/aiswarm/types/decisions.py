from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DecisionLog(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision_id: str
    timestamp: datetime
    decision_type: str
    summary: str
    agent_votes: dict[str, float]
    selected_signal_id: str | None
    selected_order_id: str | None
    risk_passed: bool
    risk_reasons: tuple[str, ...]
