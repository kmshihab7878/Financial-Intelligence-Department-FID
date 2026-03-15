from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STAGED = "staged"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"


class Order(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    signal_id: str
    symbol: str
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    notional: float = Field(gt=0)
    strategy: str
    thesis: str = Field(min_length=5)
    mandate_id: str | None = None
    risk_approval_token: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
