from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from approval_signing import sign_approval
from crypto_rules import validate_spot_signal, validate_spot_trade
from models import AccountState, ApprovedOrder, RiskDecision, Signal, TradeProposal


class RiskManager:
    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.01,
        max_position_pct: float = 0.10,
        daily_loss_limit_pct: float = 0.03,
    ) -> None:
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_position_pct = max_position_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct

    def approve_trade(
        self,
        signal: Signal,
        account_state: AccountState,
        proposal: TradeProposal | None = None,
    ) -> RiskDecision:
        try:
            validate_spot_signal(signal)
        except ValueError as exc:
            return RiskDecision(False, str(exc))

        if signal == Signal.HOLD:
            return RiskDecision(False, "HOLD signal does not require a trade")

        if proposal is None:
            return RiskDecision(False, "trade proposal is required")

        try:
            validate_spot_trade(proposal, account_state)
        except ValueError as exc:
            return RiskDecision(False, str(exc))

        if proposal.quantity <= 0 or proposal.price <= 0:
            return RiskDecision(False, "quantity and price must be positive")

        if proposal.stop_loss is None:
            return RiskDecision(False, "stop-loss is required")

        if account_state.equity <= 0 or account_state.balance < 0:
            return RiskDecision(False, "account state is invalid")

        daily_loss_limit = account_state.day_start_equity * self.daily_loss_limit_pct
        if account_state.daily_pnl <= -daily_loss_limit:
            return RiskDecision(False, "daily loss limit reached")

        max_risk = account_state.equity * self.max_risk_per_trade_pct
        if proposal.risk_amount > max_risk:
            return RiskDecision(False, "risk per trade exceeds 1% of equity")

        max_notional = account_state.equity * self.max_position_pct
        if proposal.notional > max_notional:
            return RiskDecision(False, "position notional exceeds 10% of equity")

        if proposal.notional > account_state.balance:
            return RiskDecision(False, "leverage is not allowed")

        return RiskDecision(True, "approved")

    def create_approved_order(
        self,
        signal: Signal,
        account_state: AccountState,
        proposal: TradeProposal,
    ) -> ApprovedOrder:
        decision = self.approve_trade(signal, account_state, proposal)
        if not decision.approved:
            raise ValueError(decision.reason)
        if proposal.stop_loss is None:
            raise ValueError("stop-loss is required")

        approval_id = str(uuid4())
        approval_signature = sign_approval(proposal, decision, approval_id)
        return ApprovedOrder(
            proposal=proposal,
            risk_decision=decision,
            approved_at=datetime.now(timezone.utc),
            approval_id=approval_id,
            approval_signature=approval_signature,
        )


def approve_trade(
    signal: Signal,
    account_state: AccountState,
    proposal: TradeProposal | None = None,
) -> RiskDecision:
    return RiskManager().approve_trade(signal, account_state, proposal)
