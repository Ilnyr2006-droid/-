from __future__ import annotations

import hmac
import json
from hashlib import sha256
from secrets import token_bytes

from models import ApprovedOrder, RiskDecision, TradeProposal


_APPROVAL_SIGNING_KEY = token_bytes(32)


def sign_approval(
    proposal: TradeProposal,
    risk_decision: RiskDecision,
    approval_id: str,
) -> str:
    payload = _signature_payload(proposal, risk_decision, approval_id)
    return hmac.new(_APPROVAL_SIGNING_KEY, payload, sha256).hexdigest()


def has_valid_approval_signature(approved_order: ApprovedOrder) -> bool:
    expected = sign_approval(
        approved_order.proposal,
        approved_order.risk_decision,
        approved_order.approval_id,
    )
    return hmac.compare_digest(expected, approved_order.approval_signature)


def _signature_payload(
    proposal: TradeProposal,
    risk_decision: RiskDecision,
    approval_id: str,
) -> bytes:
    payload = {
        "symbol": proposal.symbol,
        "side": proposal.side.value,
        "quantity": proposal.quantity,
        "price": proposal.price,
        "stop_loss": proposal.stop_loss,
        "take_profit": proposal.take_profit,
        "risk_decision_approved": risk_decision.approved,
        "approval_id": approval_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
