"""Tests for WebSocket broadcast and connection management."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock


from aiswarm.api.routes_ws import _clients, broadcast


class TestBroadcast:
    def setup_method(self) -> None:
        _clients.clear()

    def teardown_method(self) -> None:
        _clients.clear()

    def test_broadcast_to_no_clients(self) -> None:
        """broadcast is a no-op when no clients are connected."""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(broadcast("test", {"key": "value"}))
        loop.close()

    def test_broadcast_sends_json_to_client(self) -> None:
        """broadcast sends JSON message to connected clients."""
        ws = AsyncMock()
        _clients.add(ws)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(broadcast("signal", {"symbol": "BTCUSDT"}))
        loop.close()

        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["type"] == "signal"
        assert msg["data"]["symbol"] == "BTCUSDT"

    def test_broadcast_removes_disconnected_clients(self) -> None:
        """Clients that fail to receive are removed from the set."""
        good_ws = AsyncMock()
        bad_ws = AsyncMock()
        bad_ws.send_text.side_effect = Exception("connection closed")
        _clients.add(good_ws)
        _clients.add(bad_ws)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(broadcast("test", {}))
        loop.close()

        assert good_ws in _clients
        assert bad_ws not in _clients

    def test_broadcast_to_multiple_clients(self) -> None:
        """broadcast sends to all connected clients."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        _clients.add(ws1)
        _clients.add(ws2)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(broadcast("order", {"id": "o1"}))
        loop.close()

        assert ws1.send_text.called
        assert ws2.send_text.called
