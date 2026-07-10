from __future__ import annotations

import json
from argparse import ArgumentParser
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JournalReport:
    total_decisions: int
    filled_orders: int
    rejected_orders: int
    hold_count: int
    total_paper_pnl: float | None
    symbols_traded: list[str]
    average_risk_percent: float | None
    max_position_notional: float
    last_5_decisions: list[dict[str, Any]] = field(default_factory=list)


def generate_journal_report(journal_path: str | Path) -> JournalReport:
    records = _read_jsonl(Path(journal_path))
    total_decisions = 0
    decision_filled_orders = 0
    decision_rejected_orders = 0
    gateway_filled_orders = 0
    gateway_rejected_orders = 0
    hold_count = 0
    risk_percents: list[float] = []
    symbols_traded: set[str] = set()
    decision_symbols_traded: set[str] = set()
    seen_symbols: set[str] = set()
    max_position_notional = 0.0
    last_decisions: deque[dict[str, Any]] = deque(maxlen=5)
    account_equities: list[float] = []
    filled_order_events: list[dict[str, Any]] = []

    for record in records:
        decision = record.get("decision")
        if isinstance(decision, dict):
            total_decisions += 1
            symbol = decision.get("symbol")
            signal = decision.get("signal")
            if isinstance(symbol, str):
                seen_symbols.add(symbol)
            if signal == "HOLD":
                hold_count += 1
            order_status = decision.get("order_status")
            if order_status == "FILLED":
                decision_filled_orders += 1
                if isinstance(symbol, str):
                    decision_symbols_traded.add(symbol)
            elif order_status == "REJECTED":
                decision_rejected_orders += 1
            last_decisions.append(
                {
                    "timestamp": record.get("timestamp"),
                    "symbol": symbol,
                    "signal": signal,
                    "approved": decision.get("approved"),
                    "reason": decision.get("reason"),
                    "order_status": order_status,
                }
            )

            account = record.get("account")
            if isinstance(account, dict):
                equity = _as_float(account.get("equity"))
                if equity is not None:
                    account_equities.append(equity)
                positions = account.get("positions")
                if isinstance(positions, dict):
                    max_position_notional = max(
                        max_position_notional,
                        _max_positions_notional(positions),
                    )
                proposal = record.get("proposal")
                risk_percent = _risk_percent_from_proposal(proposal, equity)
                if risk_percent is not None:
                    risk_percents.append(risk_percent)

        if record.get("component") == "order_gateway":
            order = record.get("order")
            proposal = record.get("proposal")
            if isinstance(order, dict):
                status = order.get("status")
                symbol = order.get("symbol")
                if isinstance(symbol, str):
                    seen_symbols.add(symbol)
                if status == "FILLED":
                    gateway_filled_orders += 1
                    filled_order_events.append(order)
                    if isinstance(symbol, str):
                        symbols_traded.add(symbol)
                elif status == "REJECTED":
                    gateway_rejected_orders += 1
                max_position_notional = max(
                    max_position_notional,
                    _proposal_notional(proposal),
                )

        report_only = record.get("report")
        if isinstance(report_only, dict):
            total_decisions += 1
            symbol = report_only.get("symbol")
            signal = report_only.get("signal")
            if isinstance(symbol, str):
                seen_symbols.add(symbol)
            if signal == "HOLD":
                hold_count += 1
            risk_percent = _as_float(report_only.get("risk_percent"))
            if risk_percent is not None:
                risk_percents.append(risk_percent)
            last_decisions.append(
                {
                    "timestamp": record.get("timestamp"),
                    "symbol": symbol,
                    "signal": signal,
                    "approved": None,
                    "reason": report_only.get("reason"),
                    "order_status": None,
                }
            )

    total_paper_pnl = _paper_pnl(account_equities, filled_order_events)
    has_gateway_orders = gateway_filled_orders > 0 or gateway_rejected_orders > 0
    filled_orders = gateway_filled_orders if has_gateway_orders else decision_filled_orders
    rejected_orders = gateway_rejected_orders if has_gateway_orders else decision_rejected_orders
    reported_symbols = symbols_traded if has_gateway_orders else decision_symbols_traded
    return JournalReport(
        total_decisions=total_decisions,
        filled_orders=filled_orders,
        rejected_orders=rejected_orders,
        hold_count=hold_count,
        total_paper_pnl=total_paper_pnl,
        symbols_traded=sorted(reported_symbols or seen_symbols),
        average_risk_percent=(
            sum(risk_percents) / len(risk_percents) if risk_percents else None
        ),
        max_position_notional=max_position_notional,
        last_5_decisions=list(last_decisions),
    )


def format_journal_report(report: JournalReport) -> str:
    return json.dumps(asdict(report), indent=2)


def main() -> None:
    parser = ArgumentParser(description="Summarize a paper trading journal")
    parser.add_argument("--journal", default="journal.jsonl")
    args = parser.parse_args()
    print(format_journal_report(generate_journal_report(args.journal)))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _proposal_notional(proposal: Any) -> float:
    if not isinstance(proposal, dict):
        return 0.0
    quantity = _as_float(proposal.get("quantity"))
    price = _as_float(proposal.get("price"))
    if quantity is None or price is None:
        return 0.0
    return abs(quantity * price)


def _risk_percent_from_proposal(proposal: Any, equity: float | None) -> float | None:
    if not isinstance(proposal, dict) or equity is None or equity <= 0:
        return None
    quantity = _as_float(proposal.get("quantity"))
    price = _as_float(proposal.get("price"))
    stop_loss = _as_float(proposal.get("stop_loss"))
    if quantity is None or price is None or stop_loss is None:
        return None
    return abs(price - stop_loss) * quantity / equity * 100


def _max_positions_notional(positions: dict[str, Any]) -> float:
    max_notional = 0.0
    for position in positions.values():
        if not isinstance(position, dict):
            continue
        quantity = _as_float(position.get("quantity"))
        avg_price = _as_float(position.get("avg_price"))
        if quantity is not None and avg_price is not None:
            max_notional = max(max_notional, abs(quantity * avg_price))
    return max_notional


def _paper_pnl(
    account_equities: list[float],
    filled_order_events: list[dict[str, Any]],
) -> float | None:
    if len(account_equities) >= 2:
        return account_equities[-1] - account_equities[0]
    realized_pnl = _realized_pnl_from_orders(filled_order_events)
    return realized_pnl if filled_order_events else None


def _realized_pnl_from_orders(orders: list[dict[str, Any]]) -> float:
    positions: dict[str, tuple[float, float]] = {}
    pnl = 0.0
    for order in orders:
        symbol = order.get("symbol")
        side = order.get("side")
        quantity = _as_float(order.get("quantity"))
        price = _as_float(order.get("price"))
        if not isinstance(symbol, str) or quantity is None or price is None:
            continue
        current_quantity, avg_price = positions.get(symbol, (0.0, 0.0))
        if side == "BUY":
            new_quantity = current_quantity + quantity
            avg_price = (
                (current_quantity * avg_price + quantity * price) / new_quantity
                if new_quantity
                else 0.0
            )
            positions[symbol] = (new_quantity, avg_price)
        elif side == "SELL":
            closing_quantity = min(quantity, current_quantity)
            pnl += (price - avg_price) * closing_quantity
            positions[symbol] = (max(0.0, current_quantity - quantity), avg_price)
    return pnl


if __name__ == "__main__":
    main()
