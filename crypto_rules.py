from __future__ import annotations

import re

from models import AccountState, OrderSide, Signal, TradeProposal


DEFAULT_QUOTE_CURRENCY = "USDT"
FORBIDDEN_DERIVATIVE_MARKERS = ("PERP", "FUTURES", "SWAP")
_SPOT_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,}USDT$")


def validate_spot_symbol(symbol: str, quote_currency: str = DEFAULT_QUOTE_CURRENCY) -> None:
    normalized = symbol.upper()
    if any(marker in normalized for marker in FORBIDDEN_DERIVATIVE_MARKERS):
        raise ValueError("futures, perpetual and swap symbols are not allowed")
    if not normalized.endswith(quote_currency):
        raise ValueError(f"symbol must use {quote_currency} quote currency")
    if not _SPOT_SYMBOL_RE.fullmatch(normalized):
        raise ValueError("symbol must be a crypto spot pair like BTCUSDT")


def validate_spot_signal(signal: Signal) -> None:
    if signal not in {Signal.BUY, Signal.SELL, Signal.HOLD}:
        raise ValueError("only BUY, SELL and HOLD are allowed for spot trading")


def validate_spot_trade(proposal: TradeProposal, account_state: AccountState) -> None:
    if hasattr(proposal, "leverage"):
        raise ValueError("leverage is not allowed")
    validate_spot_symbol(proposal.symbol)
    if not isinstance(proposal.side, OrderSide):
        raise ValueError("only BUY and SELL order sides are allowed for spot trading")
    if proposal.side == OrderSide.SELL:
        position = account_state.positions.get(proposal.symbol)
        if position is None or position.quantity < proposal.quantity:
            raise ValueError("short-selling is not allowed")
