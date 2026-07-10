from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class Signal(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar high must be greater than or equal to open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar low must be less than or equal to open, close and high")
        if self.volume < 0:
            raise ValueError("bar volume cannot be negative")


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_price


@dataclass
class AccountState:
    balance: float
    equity: float
    day_start_equity: float
    positions: dict[str, Position] = field(default_factory=dict)
    market_regime: str | None = None
    volume_filter_multiplier: float = 1.0
    allow_high_volatility_research_mode: bool = False
    hold_reason: str | None = None
    feature_adx_threshold: float = 20.0
    feature_atr_volatility_threshold: float | None = None

    @property
    def daily_pnl(self) -> float:
        return self.equity - self.day_start_equity


@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    stop_loss: float | None
    take_profit: float | None = None

    @property
    def notional(self) -> float:
        return self.quantity * self.price

    @property
    def risk_amount(self) -> float:
        if self.stop_loss is None:
            return float("inf")
        return abs(self.price - self.stop_loss) * self.quantity


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


@dataclass(frozen=True)
class ApprovedOrder:
    proposal: TradeProposal
    risk_decision: RiskDecision
    approved_at: datetime
    approval_id: str
    approval_signature: str


@dataclass(frozen=True)
class Order:
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    status: OrderStatus
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }
