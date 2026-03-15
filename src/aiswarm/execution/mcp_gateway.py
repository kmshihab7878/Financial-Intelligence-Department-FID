"""MCP Gateway — abstraction for invoking MCP tools.

Provides a protocol for calling MCP tools (Aster DEX) from Python code.
Concrete implementations:
  - MockMCPGateway: For testing (returns canned responses)
  - AsterMCPGateway: For live/shadow trading (calls real Aster DEX via HTTP)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from aiswarm.resilience.circuit_breaker import CircuitBreaker
from aiswarm.resilience.rate_limiter import TokenBucketRateLimiter
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


class MCPGateway(Protocol):
    """Protocol for MCP tool invocation."""

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool and return its response."""
        ...


@dataclass
class MCPCallRecord:
    """Record of an MCP tool invocation."""

    tool_name: str
    params: dict[str, Any]
    response: dict[str, Any]
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = utc_now().isoformat()


class AsterMCPGateway:
    """Production MCP gateway — calls Aster DEX MCP server via HTTP.

    Integrates circuit breaker and rate limiter for resilience against
    exchange rate limits and outages.
    """

    def __init__(
        self,
        server_url: str,
        timeout: float = 10.0,
        rate_limit_rps: float = 5.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: float = 30.0,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.call_history: list[MCPCallRecord] = []
        self._client = httpx.Client(timeout=timeout)

        # Resilience: rate limiter + circuit breaker
        self._rate_limiter = TokenBucketRateLimiter(
            name="aster_mcp",
            max_tokens=rate_limit_rps * 2,
            refill_rate=rate_limit_rps,
        )
        self._circuit_breaker = CircuitBreaker(
            name="aster_mcp",
            failure_threshold=circuit_failure_threshold,
            recovery_timeout=circuit_recovery_timeout,
        )

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool on the Aster DEX server.

        Respects rate limits and circuit breaker. Raises on failure.
        """
        from aiswarm.monitoring import metrics as m

        # Circuit breaker check
        if not self._circuit_breaker.allow_request():
            m.ASTER_ERRORS.labels(tool=tool_name).inc()
            raise ConnectionError(f"Circuit breaker OPEN for aster_mcp — skipping {tool_name}")

        # Rate limit
        if not self._rate_limiter.wait_and_acquire(timeout=self.timeout):
            m.ASTER_ERRORS.labels(tool=tool_name).inc()
            raise TimeoutError(f"Rate limiter timeout for {tool_name}")

        start = time.monotonic()
        try:
            response = self._client.post(
                f"{self.server_url}/call-tool",
                json={"tool_name": tool_name, "params": params},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()

            self._circuit_breaker.record_success()
            elapsed = time.monotonic() - start
            m.ASTER_LATENCY.labels(tool=tool_name).observe(elapsed)

            record = MCPCallRecord(tool_name=tool_name, params=params, response=result)
            self.call_history.append(record)

            logger.info(
                "MCP call",
                extra={
                    "extra_json": {
                        "tool": tool_name,
                        "latency_ms": round(elapsed * 1000, 1),
                    }
                },
            )
            return result

        except Exception as e:
            self._circuit_breaker.record_failure()
            elapsed = time.monotonic() - start
            m.ASTER_LATENCY.labels(tool=tool_name).observe(elapsed)
            m.ASTER_ERRORS.labels(tool=tool_name).inc()

            logger.error(
                "MCP call failed",
                extra={
                    "extra_json": {
                        "tool": tool_name,
                        "error": str(e),
                        "latency_ms": round(elapsed * 1000, 1),
                    }
                },
            )
            raise

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def rate_limiter(self) -> TokenBucketRateLimiter:
        return self._rate_limiter


class MockMCPGateway:
    """Mock MCP gateway for testing. Returns configurable responses."""

    def __init__(self) -> None:
        self.call_history: list[MCPCallRecord] = []
        self._responses: dict[str, dict[str, Any]] = {}
        self._order_counter: int = 0

    def set_response(self, tool_name: str, response: dict[str, Any]) -> None:
        """Configure a response for a specific tool."""
        self._responses[tool_name] = response

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Return configured response or generate a default one."""
        if tool_name in self._responses:
            response = self._responses[tool_name]
        else:
            response = self._default_response(tool_name, params)

        record = MCPCallRecord(tool_name=tool_name, params=params, response=response)
        self.call_history.append(record)
        logger.info(
            "MockMCP call",
            extra={"extra_json": {"tool": tool_name, "params": params}},
        )
        return response

    def _default_response(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Generate default responses for common tools."""
        if "create_order" in tool_name or "create_spot_order" in tool_name:
            self._order_counter += 1
            return {
                "orderId": f"EX{self._order_counter:08d}",
                "symbol": params.get("symbol", ""),
                "side": params.get("side", ""),
                "status": "NEW",
                "type": params.get("order_type", "MARKET"),
                "origQty": str(params.get("quantity", 0)),
                "price": str(params.get("price", 0)),
            }
        if "cancel_order" in tool_name or "cancel_all" in tool_name:
            return {"success": True, "message": "Order cancelled"}
        if "set_leverage" in tool_name:
            return {
                "symbol": params.get("symbol", ""),
                "leverage": params.get("leverage", 1),
            }
        if "set_margin_mode" in tool_name:
            return {
                "symbol": params.get("symbol", ""),
                "marginMode": params.get("margin_mode", "ISOLATED"),
            }
        if "get_positions" in tool_name:
            return {"positions": []}
        if "get_balance" in tool_name:
            return {
                "totalBalance": "100000.0",
                "availableBalance": "100000.0",
                "unrealizedPnl": "0.0",
            }
        if "get_my_trades" in tool_name:
            return {"trades": []}
        if "get_order" in tool_name:
            return {
                "orderId": params.get("order_id", ""),
                "status": "FILLED",
                "symbol": params.get("symbol", ""),
            }
        return {"status": "ok"}
