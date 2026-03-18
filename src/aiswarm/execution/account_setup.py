"""Account setup service — configures leverage and margin mode before trading.

Must be called before any live orders are submitted for a symbol.
Sets margin mode to ISOLATED (safer) and leverage to the specified tier.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SetupResult:
    """Result of setting up a symbol for trading."""

    symbol: str
    leverage_set: bool
    margin_mode_set: bool
    message: str


class AccountSetupService:
    """Configures exchange account settings before trading."""

    def __init__(
        self,
        provider: ExchangeProvider,
    ) -> None:
        self.provider = provider
        self._configured_symbols: set[str] = set()

    def setup_symbol(
        self,
        symbol: str,
        leverage: int = 1,
        margin_mode: str = "ISOLATED",
    ) -> SetupResult:
        """Set leverage and margin mode for a symbol.

        Must be called before the first order on this symbol.
        """
        margin_ok = False
        leverage_ok = False
        messages: list[str] = []

        # Set margin mode first
        try:
            self.provider.set_margin_mode(symbol, margin_mode)
            margin_ok = True
        except NotImplementedError:
            # Exchange doesn't support margin mode — that's OK
            margin_ok = True
        except Exception as e:
            messages.append(f"Margin mode failed: {e}")
            logger.error(
                "Failed to set margin mode",
                extra={"extra_json": {"symbol": symbol, "error": str(e)}},
            )

        # Set leverage
        try:
            self.provider.set_leverage(symbol, leverage)
            leverage_ok = True
        except NotImplementedError:
            # Exchange doesn't support leverage — that's OK
            leverage_ok = True
        except Exception as e:
            messages.append(f"Leverage failed: {e}")
            logger.error(
                "Failed to set leverage",
                extra={"extra_json": {"symbol": symbol, "error": str(e)}},
            )

        if margin_ok and leverage_ok:
            self._configured_symbols.add(symbol)
            message = f"Symbol {symbol} configured: leverage={leverage}, margin={margin_mode}"
        else:
            message = "; ".join(messages) if messages else "Unknown error"

        logger.info(
            "Symbol setup complete",
            extra={
                "extra_json": {
                    "symbol": symbol,
                    "leverage_ok": leverage_ok,
                    "margin_ok": margin_ok,
                }
            },
        )
        return SetupResult(
            symbol=symbol,
            leverage_set=leverage_ok,
            margin_mode_set=margin_ok,
            message=message,
        )

    def setup_all_symbols(
        self,
        symbols: list[str],
        leverage: int = 1,
        margin_mode: str = "ISOLATED",
    ) -> list[SetupResult]:
        """Setup all symbols for trading."""
        return [self.setup_symbol(s, leverage, margin_mode) for s in symbols]

    def is_configured(self, symbol: str) -> bool:
        """Check if a symbol has been configured for trading."""
        return symbol in self._configured_symbols

    @property
    def configured_symbols(self) -> set[str]:
        return set(self._configured_symbols)
