from __future__ import annotations

from dataclasses import dataclass

from models import OrderSide, TradeProposal


@dataclass(frozen=True)
class ExecutionConfig:
    commission_percent: float = 0.1
    slippage_percent: float = 0.05
    spread_percent: float = 0.02
    latency_bars: int = 1

    def __post_init__(self) -> None:
        if self.commission_percent < 0:
            raise ValueError("commission_percent cannot be negative")
        if self.slippage_percent < 0:
            raise ValueError("slippage_percent cannot be negative")
        if self.spread_percent < 0:
            raise ValueError("spread_percent cannot be negative")
        if self.latency_bars < 0:
            raise ValueError("latency_bars cannot be negative")


def execution_price(
    side: OrderSide,
    reference_price: float,
    config: ExecutionConfig,
) -> float:
    slippage = reference_price * (config.slippage_percent / 100)
    half_spread = reference_price * (config.spread_percent / 100) / 2
    if side == OrderSide.BUY:
        return reference_price + slippage + half_spread
    return reference_price - slippage - half_spread


def commission_amount(notional: float, config: ExecutionConfig) -> float:
    return abs(notional) * (config.commission_percent / 100)


def execution_proposal(
    proposal: TradeProposal,
    reference_price: float,
    config: ExecutionConfig,
) -> TradeProposal:
    price = execution_price(proposal.side, reference_price, config)
    return TradeProposal(
        symbol=proposal.symbol,
        side=proposal.side,
        quantity=proposal.quantity,
        price=price,
        stop_loss=proposal.stop_loss,
        take_profit=proposal.take_profit,
    )
