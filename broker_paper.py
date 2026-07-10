from __future__ import annotations

from dataclasses import dataclass, field

from approval_signing import has_valid_approval_signature
from crypto_rules import validate_spot_symbol
from models import AccountState, ApprovedOrder, Order, OrderSide, OrderStatus, Position


@dataclass
class BrokerPaper:
    starting_balance: float = 100_000.0
    mode: str = "PAPER"
    max_position_pct: float = 0.10
    balance: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict, init=False)
    trades: list[Order] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.mode != "PAPER":
            raise ValueError("BrokerPaper supports PAPER mode only; live trading is impossible")
        if self.starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        self.balance = self.starting_balance

    @property
    def equity(self) -> float:
        return self.balance + sum(position.market_value for position in self.positions.values())

    def account_state(self) -> AccountState:
        return AccountState(
            balance=self.balance,
            equity=self.equity,
            day_start_equity=self.starting_balance,
            positions=dict(self.positions),
        )

    def submit_order(self, approved_order: ApprovedOrder) -> Order:
        if not isinstance(approved_order, ApprovedOrder):
            raise TypeError("submit_order accepts only ApprovedOrder")
        if self.mode != "PAPER":
            raise ValueError("BrokerPaper supports PAPER mode only")
        if not approved_order.risk_decision.approved:
            raise ValueError("cannot execute unapproved risk decision")

        proposal = approved_order.proposal
        symbol = proposal.symbol
        side = proposal.side
        quantity = proposal.quantity
        price = proposal.price

        if hasattr(proposal, "leverage"):
            raise ValueError("leverage is not allowed")
        validate_spot_symbol(proposal.symbol)
        if not isinstance(side, OrderSide):
            raise ValueError("only BUY and SELL order sides are allowed for spot trading")
        if proposal.stop_loss is None:
            raise ValueError("approved order must include stop-loss")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        if not has_valid_approval_signature(approved_order):
            raise ValueError("invalid approval signature")

        notional = quantity * price
        if side == OrderSide.BUY:
            max_position_size = self.equity * self.max_position_pct
            if notional > max_position_size:
                raise ValueError("approved order exceeds max paper position size")
            if notional > self.balance:
                return self._reject(symbol, side, quantity, price, "insufficient paper cash")
            self.balance -= notional
            current = self.positions.get(symbol)
            if current is None:
                self.positions[symbol] = Position(symbol, quantity, price)
            else:
                total_quantity = current.quantity + quantity
                current.avg_price = (
                    current.avg_price * current.quantity + notional
                ) / total_quantity
                current.quantity = total_quantity
        else:
            current = self.positions.get(symbol)
            if current is None or current.quantity < quantity:
                return self._reject(symbol, side, quantity, price, "insufficient paper position")
            self.balance += notional
            current.quantity -= quantity
            if current.quantity == 0:
                del self.positions[symbol]

        order = Order(symbol, side, quantity, price, OrderStatus.FILLED)
        self.trades.append(order)
        return order

    def _reject(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        reason: str,
    ) -> Order:
        order = Order(symbol, side, quantity, price, OrderStatus.REJECTED, reason)
        self.trades.append(order)
        return order
