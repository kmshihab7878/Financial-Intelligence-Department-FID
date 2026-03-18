"""MCP Gateway — abstraction for invoking MCP tools.

Provides a protocol for calling MCP tools from Python code.
Concrete implementations:
  - MockMCPGateway: For testing (returns canned responses)
  - AsterMCPGateway: Thin wrapper around HTTPMCPGateway for Aster DEX
  - HTTPMCPGateway: Generic HTTP gateway for any exchange (see http_mcp_gateway.py)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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
    """Production MCP gateway for Aster DEX.

    Thin wrapper around HTTPMCPGateway with exchange_name='aster'.
    Kept for backward compatibility — new code should use HTTPMCPGateway directly.
    """

    def __init__(
        self,
        server_url: str,
        timeout: float = 10.0,
        rate_limit_rps: float = 5.0,
        circuit_failure_threshold: int = 5,
        circuit_recovery_timeout: float = 30.0,
    ) -> None:
        from aiswarm.execution.http_mcp_gateway import HTTPMCPGateway

        self._inner = HTTPMCPGateway(
            server_url=server_url,
            exchange_name="aster",
            timeout=timeout,
            rate_limit_rps=rate_limit_rps,
            circuit_failure_threshold=circuit_failure_threshold,
            circuit_recovery_timeout=circuit_recovery_timeout,
        )

    def call_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Delegate to HTTPMCPGateway."""
        return self._inner.call_tool(tool_name, params)

    @property
    def call_history(self) -> list[MCPCallRecord]:
        return self._inner.call_history

    @property
    def circuit_breaker(self) -> Any:
        return self._inner.circuit_breaker

    @property
    def rate_limiter(self) -> Any:
        return self._inner.rate_limiter

    @property
    def server_url(self) -> str:
        return self._inner.server_url


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
