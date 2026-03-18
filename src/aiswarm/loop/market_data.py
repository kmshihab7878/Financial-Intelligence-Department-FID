"""Market data service — fetches live data via exchange provider for agent consumption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiswarm.data.providers.aster import AsterDataProvider
from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SymbolData:
    """Aggregated market data for a single symbol."""

    symbol: str
    klines_raw: Any | None = None
    funding_raw: Any | None = None
    ticker_raw: Any | None = None
    orderbook_raw: Any | None = None


class MarketDataService:
    """Fetches market data from exchange via ExchangeProvider.

    Provides structured data contexts for agents to consume.
    """

    def __init__(
        self,
        provider: ExchangeProvider,
    ) -> None:
        self.provider = provider
        # Keep a parser for liquidity computation
        self._data_provider = AsterDataProvider()

    def fetch_symbol_data(
        self,
        symbol: str,
        klines_interval: str = "1h",
        klines_limit: int = 100,
    ) -> SymbolData:
        """Fetch all market data for a symbol.

        Calls klines, funding rate, ticker, and order book via provider.
        Returns raw responses for agents to parse.
        """
        klines = self.provider.get_klines(symbol, klines_interval, klines_limit)
        funding = self.provider.get_funding_rate(symbol)
        ticker = self.provider.get_ticker(symbol)
        orderbook = self.provider.get_order_book(symbol)

        # Convert parsed types back to raw-like format for agent context
        # (agents expect raw dicts in their context)
        klines_raw = (
            [
                {
                    "openTime": int(k.timestamp.timestamp() * 1000),
                    "open": str(k.open),
                    "high": str(k.high),
                    "low": str(k.low),
                    "close": str(k.close),
                    "volume": str(k.volume),
                }
                for k in klines
            ]
            if klines
            else None
        )

        funding_raw = (
            {
                "symbol": funding.symbol,
                "lastFundingRate": str(funding.funding_rate),
                "markPrice": str(funding.mark_price),
            }
            if funding
            else None
        )

        ticker_raw = (
            {
                "symbol": ticker.symbol,
                "lastPrice": str(ticker.last_price),
                "highPrice": str(ticker.high_24h),
                "lowPrice": str(ticker.low_24h),
                "volume": str(ticker.volume_24h),
                "priceChangePercent": str(ticker.price_change_pct),
            }
            if ticker
            else None
        )

        orderbook_raw = (
            {
                "bids": [[str(b.price), str(b.quantity)] for b in orderbook.bids],
                "asks": [[str(a.price), str(a.quantity)] for a in orderbook.asks],
            }
            if orderbook
            else None
        )

        return SymbolData(
            symbol=symbol,
            klines_raw=klines_raw,
            funding_raw=funding_raw,
            ticker_raw=ticker_raw,
            orderbook_raw=orderbook_raw,
        )

    def build_agent_context(self, data: SymbolData) -> dict[str, Any]:
        """Build context dict for agents from fetched market data."""
        ctx: dict[str, Any] = {"symbol": data.symbol}
        if data.klines_raw is not None:
            ctx["klines_data"] = data.klines_raw
        if data.funding_raw is not None:
            ctx["funding_data"] = data.funding_raw
        if data.ticker_raw is not None:
            ctx["ticker_data"] = data.ticker_raw
        if data.orderbook_raw is not None:
            ctx["orderbook_data"] = data.orderbook_raw
        return ctx

    def compute_liquidity_score(self, data: SymbolData, notional: float = 10000.0) -> float:
        """Compute liquidity score from order book data."""
        if data.orderbook_raw is None:
            return 0.5  # Default moderate score
        orderbook = self._data_provider.parse_orderbook_response(data.orderbook_raw, data.symbol)
        if orderbook is None:
            return 0.5
        return float(self._data_provider.compute_liquidity_score(orderbook, notional))
