from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class MarketRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    TRANSITION = "transition"
    STRESSED = "stressed"


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_id: str
    agent_id: str
    symbol: str
    strategy: str
    thesis: str = Field(min_length=5)
    direction: int = Field(ge=-1, le=1)
    confidence: float = Field(ge=0.0, le=1.0)
    expected_return: float
    horizon_minutes: int = Field(gt=0)
    liquidity_score: float = Field(ge=0.0, le=1.0)
    regime: MarketRegime
    created_at: datetime
    reference_price: float = 0.0
