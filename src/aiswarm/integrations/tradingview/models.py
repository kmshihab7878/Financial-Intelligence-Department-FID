"""Pydantic models for TradingView webhook payloads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TVAlertPayload(BaseModel):
    """TradingView alert webhook payload.

    TradingView sends JSON payloads when alert conditions are met.
    This model validates the expected fields.
    """

    symbol: str
    action: str = Field(description="buy, sell, or flat")
    strategy: str = "tradingview"
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    price: float = Field(default=0.0, ge=0.0)
    thesis: str = Field(default="TradingView alert signal", min_length=5)
    timeframe: str = "1h"
    exchange: str = ""
    passphrase: str = ""

    model_config = {"extra": "forbid"}
