from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict


class RiskSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RiskEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str
    severity: RiskSeverity
    rule: str
    message: str
    symbol: str | None
    strategy: str | None
    created_at: datetime
