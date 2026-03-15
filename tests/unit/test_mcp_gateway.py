"""Tests for the MCP gateway abstraction."""

from __future__ import annotations

from aiswarm.execution.mcp_gateway import MockMCPGateway


class TestMockMCPGateway:
    def test_default_create_order_response(self) -> None:
        gateway = MockMCPGateway()
        response = gateway.call_tool(
            "mcp__aster__create_order",
            {"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1},
        )
        assert "orderId" in response
        assert response["orderId"].startswith("EX")

    def test_custom_response(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__aster__get_balance", {"totalBalance": "999.0"})
        response = gateway.call_tool("mcp__aster__get_balance", {})
        assert response["totalBalance"] == "999.0"

    def test_call_history(self) -> None:
        gateway = MockMCPGateway()
        gateway.call_tool("mcp__aster__get_positions", {})
        gateway.call_tool("mcp__aster__get_balance", {})

        assert len(gateway.call_history) == 2
        assert gateway.call_history[0].tool_name == "mcp__aster__get_positions"
        assert gateway.call_history[1].tool_name == "mcp__aster__get_balance"

    def test_default_cancel_response(self) -> None:
        gateway = MockMCPGateway()
        response = gateway.call_tool("mcp__aster__cancel_order", {"order_id": "123"})
        assert response["success"]

    def test_order_counter_increments(self) -> None:
        gateway = MockMCPGateway()
        r1 = gateway.call_tool("mcp__aster__create_order", {"symbol": "BTCUSDT"})
        r2 = gateway.call_tool("mcp__aster__create_order", {"symbol": "ETHUSDT"})
        assert r1["orderId"] != r2["orderId"]

    def test_default_leverage_response(self) -> None:
        gateway = MockMCPGateway()
        response = gateway.call_tool(
            "mcp__aster__set_leverage",
            {"symbol": "BTCUSDT", "leverage": 5},
        )
        assert response["leverage"] == 5
