"""TradingView webhook handler — FastAPI router for ingesting TV alerts.

Receives TradingView alert payloads, validates authentication, converts
them to AIS Signal objects, and injects them into the coordinator's
external signal queue.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from aiswarm.integrations.tradingview.auth import validate_webhook_passphrase
from aiswarm.integrations.tradingview.models import TVAlertPayload
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.utils.ids import new_id
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["tradingview"])

# Thread-safe queue for external signals
_signal_queue: deque[Signal] = deque(maxlen=100)
_queue_lock = threading.Lock()

# Timeframe-to-minutes mapping
_TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def _action_to_direction(action: str) -> int:
    """Convert TV action string to AIS direction integer."""
    action = action.lower().strip()
    if action in ("buy", "long"):
        return 1
    if action in ("sell", "short"):
        return -1
    return 0  # flat / close


def _tv_to_signal(payload: TVAlertPayload) -> Signal:
    """Convert a TradingView alert payload to an AIS Signal."""
    horizon = _TIMEFRAME_MINUTES.get(payload.timeframe, 60)
    direction = _action_to_direction(payload.action)

    return Signal(
        signal_id=new_id("tv"),
        agent_id="tradingview_webhook",
        symbol=payload.symbol,
        strategy=payload.strategy,
        thesis=payload.thesis,
        direction=direction,
        confidence=payload.confidence,
        expected_return=0.005 * direction,  # default 0.5% expected return
        horizon_minutes=horizon,
        liquidity_score=0.8,  # default moderate liquidity
        regime=MarketRegime.RISK_ON,
        created_at=utc_now(),
        reference_price=payload.price,
    )


@router.post("/tradingview")
async def receive_tradingview_alert(request: Request) -> dict[str, Any]:
    """Receive and process a TradingView webhook alert.

    Validates the passphrase, converts the payload to a Signal,
    and enqueues it for the trading loop to consume.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.warning("TradingView webhook invalid JSON", extra={"extra_json": {"error": str(e)}})
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        payload = TVAlertPayload(**body)
    except Exception as e:
        logger.warning(
            "TradingView webhook invalid payload", extra={"extra_json": {"error": str(e)}}
        )
        raise HTTPException(status_code=422, detail="Invalid payload format")

    # Authentication
    if not validate_webhook_passphrase(payload.passphrase):
        logger.warning(
            "TradingView webhook auth failed",
            extra={"extra_json": {"symbol": payload.symbol}},
        )
        raise HTTPException(status_code=401, detail="Invalid passphrase")

    # Convert to Signal
    signal = _tv_to_signal(payload)

    # Enqueue (maxlen=100 drops oldest signals if full)
    with _queue_lock:
        was_full = len(_signal_queue) >= (_signal_queue.maxlen or 100)
        _signal_queue.append(signal)
        if was_full:
            logger.warning(
                "TradingView signal queue full — oldest signal dropped",
                extra={"extra_json": {"queue_size": len(_signal_queue)}},
            )

    logger.info(
        "TradingView signal received",
        extra={
            "extra_json": {
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "confidence": signal.confidence,
            }
        },
    )

    return {
        "status": "accepted",
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "direction": signal.direction,
    }


def drain_signals() -> list[Signal]:
    """Drain all pending TradingView signals from the queue.

    Called by the trading loop each cycle to collect external signals.
    Thread-safe.
    """
    with _queue_lock:
        signals = list(_signal_queue)
        _signal_queue.clear()
    return signals


def pending_count() -> int:
    """Return the number of pending signals in the queue."""
    with _queue_lock:
        return len(_signal_queue)
