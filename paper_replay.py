from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from broker_paper import BrokerPaper
from data_provider import DataProvider
from market_regime import detect_market_regime
from models import Bar, OrderStatus, Signal, TradeProposal
from order_gateway import OrderGateway
from risk_manager import RiskManager
from strategies import create_strategy
from strategies.base import Strategy


@dataclass(frozen=True)
class PaperReplayReport:
    symbol: str
    strategy: str
    params: dict[str, Any]
    starting_balance: float
    ending_balance: float
    net_pnl: float
    net_pnl_percent: float
    filled_orders: int
    rejected_orders: int
    hold_count: int
    max_drawdown: float
    final_positions: dict[str, dict[str, float | str]]
    journal_path: str
    config_path: str | None = None
    config_selected_at: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class FrozenReplayConfig:
    strategy: str
    params: dict[str, Any]
    selected_at: str
    source_data_dir: str
    config_path: str
    warning: str | None


def load_frozen_replay_config(
    config_path: str | Path,
    csv_path: str | Path,
) -> FrozenReplayConfig:
    path = Path(config_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("allowed_next_mode") != "paper_replay":
        raise ValueError("selected candidate config does not allow paper_replay")
    strategy = payload.get("strategy")
    if strategy is None:
        raise ValueError("selected candidate config has no selected strategy")
    if not isinstance(strategy, str):
        raise ValueError("selected candidate config strategy must be a string")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("selected candidate config params must be an object")
    selected_at = payload.get("selected_at")
    if not isinstance(selected_at, str) or not selected_at:
        raise ValueError("selected candidate config selected_at is required")
    source_data_dir = payload.get("source_data_dir")
    if not isinstance(source_data_dir, str) or not source_data_dir:
        raise ValueError("selected candidate config source_data_dir is required")
    warning = _csv_source_warning(csv_path, source_data_dir)
    return FrozenReplayConfig(
        strategy=strategy,
        params=params,
        selected_at=selected_at,
        source_data_dir=source_data_dir,
        config_path=str(path),
        warning=warning,
    )


def run_paper_replay(
    symbol: str,
    csv_path: str | Path,
    strategy_name: str = "ema_crossover",
    strategy_params: dict[str, Any] | None = None,
    timeframe: str = "1h",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    journal_path: str | Path = "journal_replay.jsonl",
    bars: list[Bar] | None = None,
    strategy: Strategy | None = None,
    broker: BrokerPaper | None = None,
    order_gateway: OrderGateway | None = None,
    config_path: str | Path | None = None,
    config_selected_at: str | None = None,
    warning: str | None = None,
) -> PaperReplayReport:
    replay_bars = bars or DataProvider().get_bars(
        symbol,
        timeframe,
        limit,
        data_source="csv",
        csv_path=csv_path,
    )
    paper_broker = broker or BrokerPaper(starting_balance=starting_balance)
    if paper_broker.mode != "PAPER":
        raise ValueError("paper_replay requires BrokerPaper PAPER mode")
    risk_manager = RiskManager()
    gateway = order_gateway or OrderGateway(paper_broker, risk_manager, journal_path)
    params = strategy_params or {}
    active_strategy = strategy or create_strategy(
        strategy_name,
        symbol,
        **_strategy_kwargs(strategy_name, params),
    )

    filled_orders = 0
    rejected_orders = 0
    hold_count = 0
    equity_curve: list[float] = [starting_balance]
    journal = Path(journal_path)
    journal.parent.mkdir(parents=True, exist_ok=True)

    for idx, bar in enumerate(replay_bars):
        window = replay_bars[: idx + 1]
        account_state = paper_broker.account_state()
        account_state.market_regime = detect_market_regime(window).value
        output = active_strategy.generate_signal(window, account_state)
        if isinstance(output, TradeProposal):
            order = gateway.execute(output)
            if order.status == OrderStatus.FILLED:
                filled_orders += 1
            elif order.status == OrderStatus.REJECTED:
                rejected_orders += 1
            _append_replay_journal(
                journal,
                {
                    "event": "paper_replay_decision",
                    "timestamp": bar.timestamp.isoformat(),
                    "symbol": symbol,
                    "strategy": active_strategy.name,
                    "params": params,
                    "config_path": str(config_path) if config_path is not None else None,
                    "config_selected_at": config_selected_at,
                    "signal": output.side.value,
                    "proposal": asdict(output),
                    "order": order.to_dict(),
                    "account": _account_payload(paper_broker, bar.close),
                },
            )
        elif output == Signal.HOLD:
            hold_count += 1
            _append_replay_journal(
                journal,
                {
                    "event": "paper_replay_decision",
                    "timestamp": bar.timestamp.isoformat(),
                    "symbol": symbol,
                    "strategy": active_strategy.name,
                    "params": params,
                    "config_path": str(config_path) if config_path is not None else None,
                    "config_selected_at": config_selected_at,
                    "signal": Signal.HOLD.value,
                    "hold_reason": account_state.hold_reason,
                    "proposal": None,
                    "order": None,
                    "account": _account_payload(paper_broker, bar.close),
                },
            )
        else:
            raise ValueError("strategy must return TradeProposal or Signal.HOLD")

        equity_curve.append(_mark_to_market_equity(paper_broker, bar.close))

    ending_balance = equity_curve[-1]
    final_positions = {
        position_symbol: {
            "symbol": position.symbol,
            "quantity": position.quantity,
            "avg_price": position.avg_price,
        }
        for position_symbol, position in paper_broker.positions.items()
    }
    return PaperReplayReport(
        symbol=symbol,
        strategy=active_strategy.name,
        params=params,
        starting_balance=starting_balance,
        ending_balance=ending_balance,
        net_pnl=ending_balance - starting_balance,
        net_pnl_percent=((ending_balance - starting_balance) / starting_balance * 100),
        filled_orders=filled_orders,
        rejected_orders=rejected_orders,
        hold_count=hold_count,
        max_drawdown=_max_drawdown(equity_curve),
        final_positions=final_positions,
        journal_path=str(journal),
        config_path=str(config_path) if config_path is not None else None,
        config_selected_at=config_selected_at,
        warning=warning,
    )


def format_paper_replay_report(report: PaperReplayReport) -> str:
    return json.dumps(asdict(report), indent=2)


def _append_replay_journal(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _strategy_kwargs(strategy_name: str, params: dict[str, Any]) -> dict[str, Any]:
    if strategy_name == "ema_crossover":
        kwargs: dict[str, Any] = {}
        if "fast_ema" in params:
            kwargs["fast_period"] = params["fast_ema"]
        if "slow_ema" in params:
            kwargs["slow_period"] = params["slow_ema"]
        return kwargs
    return dict(params)


def _csv_source_warning(csv_path: str | Path, source_data_dir: str) -> str | None:
    csv_resolved = Path(csv_path).resolve()
    source_resolved = Path(source_data_dir).resolve()
    if csv_resolved.is_relative_to(source_resolved):
        return None
    return "CSV file is not from selected candidate source_data_dir"


def _account_payload(broker: BrokerPaper, mark_price: float) -> dict[str, Any]:
    return {
        "balance": broker.balance,
        "equity": _mark_to_market_equity(broker, mark_price),
        "positions": {
            symbol: {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
            }
            for symbol, position in broker.positions.items()
        },
    }


def _mark_to_market_equity(broker: BrokerPaper, mark_price: float) -> float:
    return broker.balance + sum(
        position.quantity * mark_price for position in broker.positions.values()
    )


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        worst = max(worst, drawdown)
    return worst
