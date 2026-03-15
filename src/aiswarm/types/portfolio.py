from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    quantity: float
    avg_price: float = Field(gt=0)
    market_price: float = Field(gt=0)
    strategy: str

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: datetime
    nav: float = Field(gt=0)
    cash: float
    gross_exposure: float = Field(ge=0)
    net_exposure: float
    positions: tuple[Position, ...]
