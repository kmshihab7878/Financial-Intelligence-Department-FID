"""Exchange configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExchangeConfig(BaseModel):
    """Configuration for a single exchange."""

    exchange_id: str
    enabled: bool = True
    mcp_server_url: str = ""
    is_default: bool = False
    rate_limit_rps: float = Field(default=5.0, ge=0.1)
    timeout_seconds: float = Field(default=10.0, ge=1.0)
    account_id: str = ""
    symbols: list[str] = []

    model_config = {"extra": "forbid"}


class ExchangesConfig(BaseModel):
    """Top-level exchanges configuration."""

    exchanges: list[ExchangeConfig] = []

    model_config = {"extra": "forbid"}
