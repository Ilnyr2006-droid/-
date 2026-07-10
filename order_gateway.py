from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from broker_paper import BrokerPaper
from models import Order, OrderStatus, Signal, TradeProposal
from risk_manager import RiskManager


class OrderGateway:
    """Single safe gateway for paper order execution."""

    def __init__(
        self,
        broker: BrokerPaper,
        risk_manager: RiskManager,
        journal_path: str | Path | None = "journal.jsonl",
    ) -> None:
        self.broker = broker
        self.risk_manager = risk_manager
        self.journal_path = Path(journal_path) if journal_path is not None else None

    def execute(self, proposal: TradeProposal) -> Order:
        signal = Signal(proposal.side.value)
        account_state = self.broker.account_state()
        decision = self.risk_manager.approve_trade(signal, account_state, proposal)

        if not decision.approved:
            rejected = Order(
                symbol=proposal.symbol,
                side=proposal.side,
                quantity=proposal.quantity,
                price=proposal.price,
                status=OrderStatus.REJECTED,
                reason=decision.reason,
            )
            self._log_execution(proposal, decision.reason, None, rejected)
            return rejected

        approved_order = self.risk_manager.create_approved_order(signal, account_state, proposal)
        order = self.broker.submit_order(approved_order)
        self._log_execution(proposal, decision.reason, approved_order.approval_id, order)
        return order

    def _log_execution(
        self,
        proposal: TradeProposal,
        reason: str,
        approval_id: str | None,
        order: Order,
    ) -> None:
        if self.journal_path is None:
            return
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": "order_gateway",
            "proposal": asdict(proposal),
            "reason": reason,
            "approval_id": approval_id,
            "order": order.to_dict(),
        }
        with self.journal_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
