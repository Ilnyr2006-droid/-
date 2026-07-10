from __future__ import annotations

import json
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

from broker_paper import BrokerPaper
from data_provider import DataProvider
from execution_model import (
    ExecutionConfig,
    commission_amount,
    execution_price,
    execution_proposal,
)
from market_regime import detect_market_regime
from models import Bar, OrderStatus, Signal, TradeProposal
from order_gateway import OrderGateway
from risk_manager import RiskManager
from research_config import ResearchConfig, load_research_config
from research.feature_filters import FeatureFilterConfig, apply_feature_filter_config
from strategies import STRATEGY_REGISTRY, create_strategy
from strategies.base import Strategy


@dataclass(frozen=True)
class BacktestResult:
    config: dict[str, Any]
    strategy: str
    symbol: str
    starting_balance: float
    ending_balance: float
    pnl: float
    pnl_percent: float
    gross_pnl: float
    net_pnl: float
    net_pnl_percent: float
    total_commission_paid: float
    average_slippage_cost: float
    number_of_trades: int
    winrate: float
    max_drawdown: float
    sharpe_like: float
    rejected_trades_count: int
    final_positions: dict[str, dict[str, float | str]]
    risk_settings: dict[str, float]
    trades: list[dict[str, Any]]
    rejected_trades: list[dict[str, Any]]
    final_account_state: dict[str, Any]
    equity_curve: list[dict[str, float | str]]
    drawdown_curve: list[dict[str, float | str]]


@dataclass(frozen=True)
class WalkForwardSegment:
    train_period: dict[str, str]
    test_period: dict[str, str]
    pnl_train: float
    pnl_test: float
    max_drawdown_test: float
    winrate_test: float
    stable: bool


@dataclass(frozen=True)
class WalkForwardReport:
    symbol: str
    strategy: str
    timeframe: str
    stable: bool
    segments: list[WalkForwardSegment]


@dataclass(frozen=True)
class RobustnessReport:
    strategy: str
    data_dir: str
    datasets: list[dict[str, Any]]
    summary: dict[str, Any]


@dataclass(frozen=True)
class CandidateSelectionReport:
    selected_strategy: str | None
    selected_params: dict[str, Any] | None
    reason: str
    rejected_candidates: list[dict[str, Any]]
    warnings: list[str]
    next_recommended_mode: str


@dataclass(frozen=True)
class SelectedCandidateConfig:
    strategy: str | None
    params: dict[str, Any] | None
    selected_at: str
    source_data_dir: str
    validation_summary: dict[str, Any]
    robustness_summary: dict[str, Any]
    warnings: list[str]
    allowed_next_mode: str


def run_backtest(
    bars: list[Bar],
    symbol: str,
    starting_balance: float = 100_000.0,
    strategy_name: str = "ema_crossover",
    strategy: Strategy | None = None,
    strategy_kwargs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    execution_config: ExecutionConfig = ExecutionConfig(),
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
    feature_filter_config: FeatureFilterConfig | None = None,
    journal_path: str | Path | None = "work/backtest_journal.jsonl",
) -> BacktestResult:
    strategy_kwargs = strategy_kwargs or {}
    active_strategy = strategy or create_strategy(strategy_name, symbol, **strategy_kwargs)
    validation_settings = _validation_settings(validation_mode, research_config)
    risk = RiskManager()
    broker = BrokerPaper(starting_balance=starting_balance)
    gateway = OrderGateway(broker, risk, journal_path=journal_path)
    equity_curve: list[float] = [starting_balance]
    equity_curve_points: list[dict[str, float | str]] = [
        {
            "timestamp": bars[0].timestamp.isoformat() if bars else "",
            "equity": starting_balance,
        }
    ]
    closed_pnls: list[float] = []
    entry_prices: dict[str, float] = {}
    entry_records: dict[str, dict[str, Any]] = {}
    filled_trades = 0
    rejected_trades = 0
    total_commission_paid = 0.0
    slippage_costs: list[float] = []
    filled_trade_records: list[dict[str, Any]] = []
    rejected_trade_records: list[dict[str, Any]] = []
    pending: list[tuple[int, int, TradeProposal]] = []

    for idx, bar in enumerate(bars):
        price = bar.close
        executable = [item for item in pending if item[0] == idx]
        pending = [item for item in pending if item[0] > idx]

        for _, signal_idx, proposal in executable:
            adjusted_proposal = execution_proposal(proposal, price, execution_config)
            order = gateway.execute(adjusted_proposal)
            if order.status == OrderStatus.FILLED:
                filled_trades += 1
                notional = adjusted_proposal.notional
                commission = commission_amount(notional, execution_config)
                broker.balance -= commission
                total_commission_paid += commission
                slippage_cost = abs(adjusted_proposal.price - price) * adjusted_proposal.quantity
                slippage_costs.append(slippage_cost)
                record = order.to_dict()
                record.update(
                    {
                        "signal_bar_index": signal_idx,
                        "execution_bar_index": idx,
                        "signal_price": proposal.price,
                        "reference_price": price,
                        "execution_price": adjusted_proposal.price,
                        "commission": commission,
                        "slippage_cost": slippage_cost,
                        "execution_config": asdict(execution_config),
                    }
                )
                filled_trade_records.append(record)
                if proposal.side.value == "BUY":
                    entry_prices[proposal.symbol] = adjusted_proposal.price
                    record.update(
                        {
                            "entry_time": bar.timestamp.isoformat(),
                            "exit_time": None,
                            "entry_price": adjusted_proposal.price,
                            "exit_price": None,
                            "pnl": None,
                        }
                    )
                    entry_records[proposal.symbol] = {
                        "symbol": proposal.symbol,
                        "entry_time": bar.timestamp.isoformat(),
                        "exit_time": None,
                        "entry_price": adjusted_proposal.price,
                        "exit_price": None,
                        "quantity": proposal.quantity,
                        "commission": commission,
                        "slippage_cost": slippage_cost,
                        "pnl": None,
                    }
                elif proposal.symbol in entry_prices:
                    trade_pnl = (
                        adjusted_proposal.price - entry_prices[proposal.symbol]
                    ) * proposal.quantity
                    closed_pnls.append(trade_pnl)
                    entry_record = entry_records.pop(proposal.symbol, None)
                    if entry_record is not None:
                        record.update(
                            {
                                "entry_time": entry_record["entry_time"],
                                "exit_time": bar.timestamp.isoformat(),
                                "entry_price": entry_record["entry_price"],
                                "exit_price": adjusted_proposal.price,
                                "commission": entry_record["commission"] + commission,
                                "slippage_cost": entry_record["slippage_cost"] + slippage_cost,
                                "pnl": trade_pnl - entry_record["commission"] - commission,
                            }
                        )
                    del entry_prices[proposal.symbol]
            elif order.status == OrderStatus.REJECTED:
                rejected_trades += 1
                record = order.to_dict()
                record.update(
                    {
                        "signal_bar_index": signal_idx,
                        "execution_bar_index": idx,
                        "signal_price": proposal.price,
                        "reference_price": price,
                    }
                )
                rejected_trade_records.append(record)

        window = bars[: idx + 1]
        account_state = broker.account_state()
        account_state.market_regime = detect_market_regime(window).value
        account_state.volume_filter_multiplier = validation_settings.volume_filter_multiplier
        account_state.allow_high_volatility_research_mode = (
            validation_settings.allow_high_volatility_research_mode
        )
        apply_feature_filter_config(account_state, feature_filter_config)
        strategy_output = active_strategy.generate_signal(window, account_state)

        if isinstance(strategy_output, TradeProposal):
            execute_idx = idx + execution_config.latency_bars
            has_pending_symbol = any(
                pending_proposal.symbol == strategy_output.symbol
                for _, _, pending_proposal in pending
            )
            if execute_idx < len(bars) and not has_pending_symbol:
                pending.append((execute_idx, idx, strategy_output))
        elif strategy_output != Signal.HOLD:
            raise ValueError("strategy must return TradeProposal or Signal.HOLD")

        mark_to_market = broker.balance + sum(
            position.quantity * price for position in broker.positions.values()
        )
        equity_curve.append(mark_to_market)
        equity_curve_points.append(
            {
                "timestamp": bar.timestamp.isoformat(),
                "equity": mark_to_market,
            }
        )

    net_pnl = equity_curve[-1] - starting_balance
    gross_pnl = net_pnl + total_commission_paid
    drawdown_curve = _drawdown_curve(equity_curve_points)
    max_drawdown = max((float(point["drawdown"]) for point in drawdown_curve), default=0.0)
    returns = [
        (equity_curve[idx] - equity_curve[idx - 1]) / equity_curve[idx - 1]
        for idx in range(1, len(equity_curve))
        if equity_curve[idx - 1] > 0
    ]
    sharpe_like = _sharpe_like(returns)
    winrate = (
        sum(1 for trade_pnl in closed_pnls if trade_pnl > 0) / len(closed_pnls)
        if closed_pnls
        else 0.0
    )
    final_positions = {
        position_symbol: {
            "symbol": position.symbol,
            "quantity": position.quantity,
            "avg_price": position.avg_price,
        }
        for position_symbol, position in broker.positions.items()
    }
    final_account_state = {
        "balance": broker.balance,
        "equity": equity_curve[-1],
        "day_start_equity": starting_balance,
        "positions": final_positions,
    }
    risk_settings = {
        "max_risk_per_trade_pct": risk.max_risk_per_trade_pct,
        "max_position_pct": risk.max_position_pct,
        "daily_loss_limit_pct": risk.daily_loss_limit_pct,
    }

    return BacktestResult(
        config=config
        or {
            "symbol": symbol,
            "starting_balance": starting_balance,
            "strategy": active_strategy.name,
            "strategy_kwargs": strategy_kwargs,
            "execution": asdict(execution_config),
        },
        strategy=active_strategy.name,
        symbol=symbol,
        starting_balance=starting_balance,
        ending_balance=equity_curve[-1],
        pnl=net_pnl,
        pnl_percent=(net_pnl / starting_balance * 100) if starting_balance else 0.0,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        net_pnl_percent=(net_pnl / starting_balance * 100) if starting_balance else 0.0,
        total_commission_paid=total_commission_paid,
        average_slippage_cost=(
            sum(slippage_costs) / len(slippage_costs) if slippage_costs else 0.0
        ),
        number_of_trades=filled_trades,
        winrate=winrate,
        max_drawdown=max_drawdown,
        sharpe_like=sharpe_like,
        rejected_trades_count=rejected_trades,
        final_positions=final_positions,
        risk_settings=risk_settings,
        trades=filled_trade_records,
        rejected_trades=rejected_trade_records,
        final_account_state=final_account_state,
        equity_curve=equity_curve_points,
        drawdown_curve=drawdown_curve,
    )


def run_backtest_for_symbol(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    strategy_name: str = "ema_crossover",
    strategy_kwargs: dict[str, Any] | None = None,
    execution_config: ExecutionConfig = ExecutionConfig(),
    data_source: str = "mock",
    csv_path: str | Path | None = None,
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
) -> BacktestResult:
    bars = DataProvider().get_bars(
        symbol,
        timeframe,
        limit,
        data_source=data_source,
        csv_path=csv_path,
    )
    config = {
        "symbol": symbol,
        "timeframe": timeframe,
        "limit": limit,
        "starting_balance": starting_balance,
        "strategy": strategy_name,
        "strategy_kwargs": strategy_kwargs or {},
        "data_source": data_source,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "execution": asdict(execution_config),
        "validation_mode": validation_mode,
    }
    return run_backtest(
        bars,
        symbol,
        starting_balance=starting_balance,
        strategy_name=strategy_name,
        strategy_kwargs=strategy_kwargs,
        config=config,
        execution_config=execution_config,
        validation_mode=validation_mode,
        research_config=research_config,
    )


def compare_strategies(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    execution_config: ExecutionConfig = ExecutionConfig(),
    data_source: str = "mock",
    csv_path: str | Path | None = None,
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
) -> list[dict[str, float | int | str | bool]]:
    validation_settings = _validation_settings(validation_mode, research_config)
    train_size, test_size = _walk_forward_sizes(validation_mode, validation_settings, 60, 30)
    requested_limit = max(limit, train_size + test_size)
    bars = DataProvider().get_bars(
        symbol,
        timeframe,
        requested_limit,
        data_source=data_source,
        csv_path=csv_path,
    )
    results: list[dict[str, float | int | str | bool]] = []
    for strategy_name in STRATEGY_REGISTRY:
        result = run_backtest(
            bars,
            symbol,
            starting_balance=starting_balance,
            strategy_name=strategy_name,
            strategy_kwargs=None,
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
        )
        walk_forward = run_walk_forward(
            symbol=symbol,
            strategy_name=strategy_name,
            timeframe=timeframe,
            limit=max(requested_limit, 180),
            starting_balance=starting_balance,
            train_size=train_size,
            test_size=test_size,
            execution_config=execution_config,
            bars=bars,
            data_source=data_source,
            csv_path=csv_path,
            validation_mode=validation_mode,
            research_config=validation_settings,
        )
        validation = validate_strategy_result(
            result,
            walk_forward,
            min_trades=(
                validation_settings.min_trades_for_timeframe(timeframe)
                if validation_mode == "research"
                else 20
            ),
        )
        results.append(
            {
                "strategy": result.strategy,
                "pnl": result.pnl,
                "pnl_percent": result.pnl_percent,
                "gross_pnl": result.gross_pnl,
                "net_pnl": result.net_pnl,
                "net_pnl_percent": result.net_pnl_percent,
                "number_of_trades": result.number_of_trades,
                "winrate": result.winrate,
                "max_drawdown": result.max_drawdown,
                "sharpe_like": result.sharpe_like,
                "rejected_trades_count": result.rejected_trades_count,
                "walk_forward_stable": walk_forward.stable,
                "valid": validation["valid"],
                "reason": validation["reason"],
            }
        )
    return results


def compare_strategies_on_data_dir(
    data_dir: str | Path,
    limit: int = 300,
    starting_balance: float = 100_000.0,
    execution_config: ExecutionConfig = ExecutionConfig(),
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
) -> list[dict[str, Any]]:
    validation_settings = _validation_settings(validation_mode, research_config)
    results: list[dict[str, Any]] = []
    for strategy_name in STRATEGY_REGISTRY:
        robustness = run_robustness(
            strategy_name=strategy_name,
            data_dir=data_dir,
            limit=limit,
            starting_balance=starting_balance,
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
        )
        results.append(
            {
                "strategy": strategy_name,
                "datasets_tested": robustness.summary["datasets_tested"],
                "valid_datasets_count": robustness.summary["valid_datasets_count"],
                "invalid_datasets_count": robustness.summary["invalid_datasets_count"],
                "average_net_pnl_percent": robustness.summary["average_net_pnl_percent"],
                "worst_drawdown": robustness.summary["worst_drawdown"],
                "robust": robustness.summary["robust"],
                "datasets": robustness.datasets,
            }
        )
    return sorted(
        results,
        key=lambda row: (bool(row["robust"]), float(row["average_net_pnl_percent"])),
        reverse=True,
    )


def save_compare_result(
    strategies_results: list[dict[str, Any]],
    symbol: str,
    timeframe: str = "1h",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    data_source: str = "mock",
    csv_path: str | Path | None = None,
    execution_config: ExecutionConfig = ExecutionConfig(),
    results_dir: str | Path = "results",
) -> Path:
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"compare_{_safe_filename_part(symbol)}_{timestamp}.json"
    valid_strategies = [row for row in strategies_results if row.get("valid") is True]
    best_valid_strategy = (
        max(valid_strategies, key=lambda row: float(row.get("net_pnl_percent", 0)))
        if valid_strategies
        else None
    )
    risk = RiskManager()
    warnings = [] if best_valid_strategy is not None else ["no valid strategies"]
    payload = {
        "config": {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "starting_balance": starting_balance,
            "data_source": data_source,
            "csv_path": str(csv_path) if csv_path is not None else None,
        },
        "execution_config": asdict(execution_config),
        "risk_settings": {
            "max_risk_per_trade_pct": risk.max_risk_per_trade_pct,
            "max_position_pct": risk.max_position_pct,
            "daily_loss_limit_pct": risk.daily_loss_limit_pct,
        },
        "strategies_results": strategies_results,
        "best_valid_strategy": best_valid_strategy,
        "warnings": warnings,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def sweep_ema_crossover(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    execution_config: ExecutionConfig = ExecutionConfig(),
    data_source: str = "mock",
    csv_path: str | Path | None = None,
) -> list[dict[str, float | int | str | bool]]:
    bars = DataProvider().get_bars(
        symbol,
        timeframe,
        limit,
        data_source=data_source,
        csv_path=csv_path,
    )
    results: list[dict[str, float | int | str | bool]] = []
    for fast_ema in (5, 10, 20):
        for slow_ema in (30, 50, 100):
            if fast_ema >= slow_ema:
                continue
            strategy_kwargs = {"fast_period": fast_ema, "slow_period": slow_ema}
            result = run_backtest(
                bars,
                symbol,
                starting_balance=starting_balance,
                strategy_name="ema_crossover",
                strategy_kwargs=strategy_kwargs,
                execution_config=execution_config,
            )
            walk_forward = run_walk_forward(
                symbol=symbol,
                strategy_name="ema_crossover",
                strategy_kwargs=strategy_kwargs,
                timeframe=timeframe,
                limit=max(limit, 180),
                starting_balance=starting_balance,
                train_size=60,
                test_size=30,
                execution_config=execution_config,
                bars=bars,
                data_source=data_source,
                csv_path=csv_path,
            )
            validation = validate_strategy_result(result, walk_forward)
            results.append(
                {
                    "strategy": "ema_crossover",
                    "fast_ema": fast_ema,
                    "slow_ema": slow_ema,
                    "net_pnl_percent": result.net_pnl_percent,
                    "net_pnl": result.net_pnl,
                    "max_drawdown": result.max_drawdown,
                    "number_of_trades": result.number_of_trades,
                    "winrate": result.winrate,
                    "sharpe_like": result.sharpe_like,
                    "rejected_trades_count": result.rejected_trades_count,
                    "walk_forward_stable": walk_forward.stable,
                    "valid": validation["valid"],
                    "reason": validation["reason"],
                }
            )
    return sorted(results, key=lambda row: float(row["net_pnl_percent"]), reverse=True)


def run_robustness(
    strategy_name: str,
    data_dir: str | Path,
    limit: int = 300,
    starting_balance: float = 100_000.0,
    execution_config: ExecutionConfig = ExecutionConfig(),
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
    strategy_kwargs: dict[str, Any] | None = None,
    feature_filter_config: FeatureFilterConfig | None = None,
) -> RobustnessReport:
    directory = Path(data_dir)
    if not directory.exists() or not directory.is_dir():
        raise ValueError(f"data_dir does not exist or is not a directory: {directory}")

    validation_settings = _validation_settings(validation_mode, research_config)
    train_size, test_size = _walk_forward_sizes(validation_mode, validation_settings, 60, 30)
    requested_limit = max(limit, train_size + test_size)
    datasets: list[dict[str, Any]] = []
    for csv_path in sorted(directory.glob("*.csv")):
        symbol, timeframe = _parse_dataset_filename(csv_path)
        bars = DataProvider().get_bars(
            symbol,
            timeframe,
            requested_limit,
            data_source="csv",
            csv_path=csv_path,
        )
        result = run_backtest(
            bars,
            symbol,
            starting_balance=starting_balance,
            strategy_name=strategy_name,
            strategy_kwargs=strategy_kwargs,
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
            feature_filter_config=feature_filter_config,
            config={
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": requested_limit,
                "starting_balance": starting_balance,
                "strategy": strategy_name,
                "data_source": "csv",
                "csv_path": str(csv_path),
                "execution": asdict(execution_config),
                "validation_mode": validation_mode,
            },
        )
        walk_forward = run_walk_forward(
            symbol=symbol,
            strategy_name=strategy_name,
            strategy_kwargs=strategy_kwargs,
            timeframe=timeframe,
            limit=max(requested_limit, 180),
            starting_balance=starting_balance,
            train_size=train_size,
            test_size=test_size,
            execution_config=execution_config,
            bars=bars,
            data_source="csv",
            csv_path=csv_path,
            validation_mode=validation_mode,
            research_config=validation_settings,
            feature_filter_config=feature_filter_config,
        )
        validation = validate_strategy_result(
            result,
            walk_forward,
            min_trades=(
                validation_settings.min_trades_for_timeframe(timeframe)
                if validation_mode == "research"
                else 20
            ),
        )
        datasets.append(
            {
                "dataset": csv_path.name,
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy": result.strategy,
                "net_pnl_percent": result.net_pnl_percent,
                "max_drawdown": result.max_drawdown,
                "number_of_trades": result.number_of_trades,
                "winrate": result.winrate,
                "walk_forward_stable": walk_forward.stable,
                "valid": validation["valid"],
                "reason": validation["reason"],
            }
        )

    summary = _robustness_summary(datasets)
    return RobustnessReport(
        strategy=strategy_name,
        data_dir=str(directory),
        datasets=datasets,
        summary=summary,
    )


def select_candidate(
    data_dir: str | Path,
    strategy_name: str = "all",
    limit: int = 300,
    starting_balance: float = 100_000.0,
    execution_config: ExecutionConfig = ExecutionConfig(),
    save_selected_config: bool = False,
    selected_config_path: str | Path = "config/selected_candidate.json",
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
) -> CandidateSelectionReport:
    if strategy_name not in {"all", *STRATEGY_REGISTRY.keys()}:
        raise ValueError("candidate selection supports 'all' or a registered strategy")

    directory = Path(data_dir)
    market_files = sorted(directory.glob("*.csv"))
    validation_settings = _validation_settings(validation_mode, research_config)
    if not market_files:
        report = CandidateSelectionReport(
            selected_strategy=None,
            selected_params=None,
            reason="no datasets available",
            rejected_candidates=[],
            warnings=["no robust strategies"],
            next_recommended_mode="report_only",
        )
        save_candidate_selection_report(report)
        if save_selected_config:
            save_selected_candidate_config(
                report=report,
                source_data_dir=directory,
                validation_summary={"valid": False, "reason": report.reason},
                robustness_summary={
                    "datasets_tested": 0,
                    "valid_datasets_count": 0,
                    "invalid_datasets_count": 0,
                    "average_net_pnl_percent": 0.0,
                    "worst_drawdown": 0.0,
                    "robust": False,
                },
                config_path=selected_config_path,
        )
        return report

    if strategy_name != "ema_crossover":
        return _select_candidate_from_robustness(
            directory=directory,
            strategy_names=STRATEGY_REGISTRY.keys() if strategy_name == "all" else [strategy_name],
            limit=limit,
            starting_balance=starting_balance,
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
            save_selected_config=save_selected_config,
            selected_config_path=selected_config_path,
        )

    first_symbol, first_timeframe = _parse_dataset_filename(market_files[0])
    sweep_results = sweep_ema_crossover(
        symbol=first_symbol,
        timeframe=first_timeframe,
        limit=limit,
        starting_balance=starting_balance,
        execution_config=execution_config,
        data_source="csv",
        csv_path=market_files[0],
    )
    robustness = run_robustness(
        strategy_name=strategy_name,
        data_dir=directory,
        limit=limit,
        starting_balance=starting_balance,
        execution_config=execution_config,
        validation_mode=validation_mode,
        research_config=validation_settings,
    )

    robust = bool(robustness.summary["robust"])
    rejected_candidates: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for candidate in sweep_results:
        rejection_reason = _candidate_rejection_reason(candidate, robust)
        if rejection_reason is None:
            eligible.append(candidate)
        else:
            rejected = dict(candidate)
            rejected["rejection_reason"] = rejection_reason
            rejected_candidates.append(rejected)

    if not eligible:
        report = CandidateSelectionReport(
            selected_strategy=None,
            selected_params=None,
            reason="no valid robust strategy",
            rejected_candidates=rejected_candidates,
            warnings=["no robust strategies"],
            next_recommended_mode="report_only",
        )
        save_candidate_selection_report(report)
        if save_selected_config:
            save_selected_candidate_config(
                report=report,
                source_data_dir=directory,
                validation_summary={"valid": False, "reason": report.reason},
                robustness_summary=robustness.summary,
                config_path=selected_config_path,
            )
        return report

    selected = max(eligible, key=lambda row: float(row["net_pnl_percent"]))
    validation_summary = {
        "valid": bool(selected["valid"]),
        "reason": str(selected["reason"]),
        "number_of_trades": int(selected["number_of_trades"]),
        "max_drawdown": float(selected["max_drawdown"]),
        "net_pnl_percent": float(selected["net_pnl_percent"]),
        "walk_forward_stable": bool(selected["walk_forward_stable"]),
        "rejected_trades_count": int(selected["rejected_trades_count"]),
    }
    report = CandidateSelectionReport(
        selected_strategy=str(selected["strategy"]),
        selected_params={
            "fast_ema": selected["fast_ema"],
            "slow_ema": selected["slow_ema"],
        },
        reason="selected best valid robust strategy by net_pnl_percent",
        rejected_candidates=rejected_candidates,
        warnings=[],
        next_recommended_mode="paper_replay",
    )
    save_candidate_selection_report(report)
    if save_selected_config:
        save_selected_candidate_config(
            report=report,
            source_data_dir=directory,
            validation_summary=validation_summary,
            robustness_summary=robustness.summary,
            config_path=selected_config_path,
        )
    return report


def _select_candidate_from_robustness(
    directory: Path,
    strategy_names: Iterable[str],
    limit: int,
    starting_balance: float,
    execution_config: ExecutionConfig,
    save_selected_config: bool,
    selected_config_path: str | Path,
    validation_mode: str,
    research_config: ResearchConfig,
) -> CandidateSelectionReport:
    candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    robustness_by_strategy: dict[str, dict[str, Any]] = {}

    for strategy_name in strategy_names:
        robustness = run_robustness(
            strategy_name=strategy_name,
            data_dir=directory,
            limit=limit,
            starting_balance=starting_balance,
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=research_config,
        )
        robustness_by_strategy[strategy_name] = robustness.summary
        min_trades = (
            min(int(row["number_of_trades"]) for row in robustness.datasets)
            if robustness.datasets
            else 0
        )
        all_stable = all(bool(row["walk_forward_stable"]) for row in robustness.datasets)
        candidate = {
            "strategy": strategy_name,
            "params": {},
            "net_pnl_percent": robustness.summary["average_net_pnl_percent"],
            "number_of_trades": min_trades,
            "max_drawdown": robustness.summary["worst_drawdown"],
            "walk_forward_stable": all_stable,
            "valid": bool(robustness.summary["robust"]),
            "reason": "passed validation" if robustness.summary["robust"] else "strategy is not robust across datasets",
            "robustness_summary": robustness.summary,
            "datasets": robustness.datasets,
        }
        rejection_reason = _candidate_rejection_reason(candidate, bool(robustness.summary["robust"]))
        if rejection_reason is None:
            candidates.append(candidate)
        else:
            rejected = dict(candidate)
            rejected["rejection_reason"] = rejection_reason
            rejected_candidates.append(rejected)

    if not candidates:
        report = CandidateSelectionReport(
            selected_strategy=None,
            selected_params=None,
            reason="no valid robust strategy",
            rejected_candidates=rejected_candidates,
            warnings=["no robust strategies"],
            next_recommended_mode="report_only",
        )
        save_candidate_selection_report(report)
        if save_selected_config:
            save_selected_candidate_config(
                report=report,
                source_data_dir=directory,
                validation_summary={"valid": False, "reason": report.reason},
                robustness_summary={
                    "strategies_tested": list(strategy_names),
                    "by_strategy": robustness_by_strategy,
                    "robust": False,
                },
                config_path=selected_config_path,
            )
        return report

    selected = max(candidates, key=lambda row: float(row["net_pnl_percent"]))
    report = CandidateSelectionReport(
        selected_strategy=str(selected["strategy"]),
        selected_params=dict(selected["params"]),
        reason="selected best valid robust strategy by average_net_pnl_percent",
        rejected_candidates=rejected_candidates,
        warnings=[],
        next_recommended_mode="paper_replay",
    )
    save_candidate_selection_report(report)
    if save_selected_config:
        save_selected_candidate_config(
            report=report,
            source_data_dir=directory,
            validation_summary={
                "valid": True,
                "reason": "passed validation",
                "number_of_trades": int(selected["number_of_trades"]),
                "max_drawdown": float(selected["max_drawdown"]),
                "net_pnl_percent": float(selected["net_pnl_percent"]),
                "walk_forward_stable": bool(selected["walk_forward_stable"]),
                "rejected_trades_count": 0,
            },
            robustness_summary=dict(selected["robustness_summary"]),
            config_path=selected_config_path,
        )
    return report


def _selected_candidate_is_tradable(
    report: CandidateSelectionReport,
    validation_summary: dict[str, Any],
    robustness_summary: dict[str, Any],
) -> bool:
    return (
        report.selected_strategy is not None
        and bool(validation_summary.get("valid"))
        and int(validation_summary.get("number_of_trades", 0)) >= 20
        and bool(validation_summary.get("walk_forward_stable"))
        and bool(robustness_summary.get("robust"))
    )


def save_selected_candidate_config(
    report: CandidateSelectionReport,
    source_data_dir: str | Path,
    validation_summary: dict[str, Any],
    robustness_summary: dict[str, Any],
    config_path: str | Path = "config/selected_candidate.json",
) -> Path:
    allowed_next_mode = (
        "paper_replay"
        if _selected_candidate_is_tradable(report, validation_summary, robustness_summary)
        else "report_only"
    )
    config = SelectedCandidateConfig(
        strategy=report.selected_strategy,
        params=report.selected_params,
        selected_at=datetime.now(timezone.utc).isoformat(),
        source_data_dir=str(source_data_dir),
        validation_summary=validation_summary,
        robustness_summary=robustness_summary,
        warnings=report.warnings,
        allowed_next_mode=allowed_next_mode,
    )
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    return path


def save_candidate_selection_report(
    report: CandidateSelectionReport,
    results_dir: str | Path = "results",
) -> Path:
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"candidate_selection_{timestamp}.json"
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return path


def format_candidate_selection_report(report: CandidateSelectionReport) -> str:
    return json.dumps(asdict(report), indent=2)


def format_robustness_report(report: RobustnessReport) -> str:
    return json.dumps(asdict(report), indent=2)


def validate_strategy_result(
    result: BacktestResult,
    walk_forward: WalkForwardReport,
    min_trades: int = 20,
    max_drawdown: float = 0.20,
    max_rejected_trade_ratio: float = 1.0,
) -> dict[str, bool | str]:
    if result.number_of_trades < min_trades:
        return {"valid": False, "reason": "too few trades"}
    if result.max_drawdown > max_drawdown:
        return {"valid": False, "reason": "max drawdown too high"}
    if result.net_pnl_percent <= 0:
        return {"valid": False, "reason": "net pnl not positive"}
    if not walk_forward.stable:
        return {"valid": False, "reason": "walk-forward unstable"}
    if result.rejected_trades_count > result.number_of_trades * max_rejected_trade_ratio:
        return {"valid": False, "reason": "too many rejected trades"}
    return {"valid": True, "reason": "passed validation"}


def run_walk_forward(
    symbol: str,
    strategy_name: str = "ema_crossover",
    strategy_kwargs: dict[str, Any] | None = None,
    timeframe: str = "1h",
    limit: int = 360,
    starting_balance: float = 100_000.0,
    train_size: int = 120,
    test_size: int = 60,
    execution_config: ExecutionConfig = ExecutionConfig(),
    bars: list[Bar] | None = None,
    data_source: str = "mock",
    csv_path: str | Path | None = None,
    validation_mode: str = "paper",
    research_config: ResearchConfig | None = None,
    feature_filter_config: FeatureFilterConfig | None = None,
) -> WalkForwardReport:
    validation_settings = _validation_settings(validation_mode, research_config)
    bars = bars or DataProvider().get_bars(
        symbol,
        timeframe,
        limit,
        data_source=data_source,
        csv_path=csv_path,
    )
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    if len(bars) < train_size + test_size:
        raise ValueError("not enough bars for one walk-forward segment")

    segments: list[WalkForwardSegment] = []
    start = 0
    while start + train_size + test_size <= len(bars):
        train_bars = bars[start : start + train_size]
        test_bars = bars[start + train_size : start + train_size + test_size]
        train_result = run_backtest(
            train_bars,
            symbol,
            starting_balance=starting_balance,
            strategy_name=strategy_name,
            strategy_kwargs=strategy_kwargs,
            config={
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy": strategy_name,
                "strategy_kwargs": strategy_kwargs or {},
                "segment": "train",
                "start_index": start,
                "end_index": start + train_size - 1,
                "execution": asdict(execution_config),
            },
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
            feature_filter_config=feature_filter_config,
        )
        test_result = run_backtest(
            test_bars,
            symbol,
            starting_balance=starting_balance,
            strategy_name=strategy_name,
            strategy_kwargs=strategy_kwargs,
            config={
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy": strategy_name,
                "strategy_kwargs": strategy_kwargs or {},
                "segment": "test",
                "start_index": start + train_size,
                "end_index": start + train_size + test_size - 1,
                "execution": asdict(execution_config),
            },
            execution_config=execution_config,
            validation_mode=validation_mode,
            research_config=validation_settings,
            feature_filter_config=feature_filter_config,
        )
        segments.append(
            WalkForwardSegment(
                train_period=_period(train_bars),
                test_period=_period(test_bars),
                pnl_train=train_result.pnl,
                pnl_test=test_result.pnl,
                max_drawdown_test=test_result.max_drawdown,
                winrate_test=test_result.winrate,
                stable=_segment_is_stable(train_result, test_result),
            )
        )
        start += test_size

    return WalkForwardReport(
        symbol=symbol,
        strategy=strategy_name,
        timeframe=timeframe,
        stable=_walk_forward_is_stable(segments),
        segments=segments,
    )


def format_backtest_report(result: BacktestResult) -> str:
    return json.dumps(asdict(result), indent=2)


def format_walk_forward_report(report: WalkForwardReport) -> str:
    return json.dumps(asdict(report), indent=2)


def save_backtest_result(
    result: BacktestResult,
    results_dir: str | Path = "results",
) -> Path:
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    strategy = _safe_filename_part(result.strategy)
    symbol = _safe_filename_part(result.symbol)
    path = output_dir / f"backtest_{strategy}_{symbol}_{timestamp}.json"
    artifact = {
        "config": result.config,
        "strategy_name": result.strategy,
        "risk_settings": result.risk_settings,
        "metrics": {
            "starting_balance": result.starting_balance,
            "ending_balance": result.ending_balance,
            "pnl": result.pnl,
            "pnl_percent": result.pnl_percent,
            "gross_pnl": result.gross_pnl,
            "net_pnl": result.net_pnl,
            "net_pnl_percent": result.net_pnl_percent,
            "total_commission_paid": result.total_commission_paid,
            "average_slippage_cost": result.average_slippage_cost,
            "number_of_trades": result.number_of_trades,
            "winrate": result.winrate,
            "max_drawdown": result.max_drawdown,
            "sharpe_like": result.sharpe_like,
            "rejected_trades_count": result.rejected_trades_count,
        },
        "trades": result.trades,
        "rejected_trades": result.rejected_trades,
        "final_account_state": result.final_account_state,
        "equity_curve": result.equity_curve,
        "drawdown_curve": result.drawdown_curve,
    }
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = ArgumentParser(description="Run paper-only strategy backtest")
    parser.add_argument("--symbol", default="MOCK")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--strategy", choices=tuple(STRATEGY_REGISTRY), default="ema_crossover")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--starting-balance", type=float, default=100_000.0)
    parser.add_argument("--save-results", action="store_true")
    parser.add_argument("--train-size", type=int, default=120)
    parser.add_argument("--test-size", type=int, default=60)
    parser.add_argument("--data-source", choices=("mock", "csv"), default="mock")
    parser.add_argument("--csv-path")
    args = parser.parse_args()

    result = run_backtest_for_symbol(
        symbol=args.symbol,
        timeframe=args.timeframe,
        limit=args.limit,
        starting_balance=args.starting_balance,
        strategy_name=args.strategy,
        data_source=args.data_source,
        csv_path=args.csv_path,
    )
    if args.save_results:
        save_backtest_result(result)
    print(format_backtest_report(result))


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        worst = max(worst, drawdown)
    return worst


def _drawdown_curve(equity_curve: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    peak = 0.0
    points: list[dict[str, float | str]] = []
    for point in equity_curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        points.append(
            {
                "timestamp": point["timestamp"],
                "drawdown": drawdown,
            }
        )
    return points


def _validation_settings(
    validation_mode: str,
    research_config: ResearchConfig | None,
) -> ResearchConfig:
    if validation_mode not in {"paper", "research"}:
        raise ValueError("validation_mode must be 'paper' or 'research'")
    if validation_mode == "research":
        return research_config or load_research_config()
    return ResearchConfig(
        walk_forward_train_size=120,
        walk_forward_test_size=60,
        min_trades_by_timeframe={
            "1m": 20,
            "5m": 20,
            "15m": 20,
            "1h": 20,
            "4h": 20,
            "1d": 20,
        },
        volume_filter_multiplier=1.0,
        allow_high_volatility_research_mode=False,
    )


def _walk_forward_sizes(
    validation_mode: str,
    research_config: ResearchConfig,
    paper_train_size: int,
    paper_test_size: int,
) -> tuple[int, int]:
    if validation_mode == "research":
        return research_config.walk_forward_train_size, research_config.walk_forward_test_size
    return paper_train_size, paper_test_size


def _safe_filename_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _period(bars: list[Bar]) -> dict[str, str]:
    return {
        "start": bars[0].timestamp.isoformat(),
        "end": bars[-1].timestamp.isoformat(),
    }


def _segment_is_stable(train_result: BacktestResult, test_result: BacktestResult) -> bool:
    if train_result.pnl > 0 and test_result.pnl <= 0:
        return False
    if test_result.max_drawdown > 0.10:
        return False
    return True


def _walk_forward_is_stable(segments: list[WalkForwardSegment]) -> bool:
    if not segments:
        return False
    profitable_tests = sum(1 for segment in segments if segment.pnl_test > 0)
    if profitable_tests <= 1 and len(segments) > 1:
        return False
    return all(segment.stable for segment in segments)


def _parse_dataset_filename(path: Path) -> tuple[str, str]:
    parts = path.stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in {"1m", "5m", "15m", "1h", "4h", "1d"}:
        return parts[0], parts[1]
    return path.stem, "1h"


def _robustness_summary(datasets: list[dict[str, Any]]) -> dict[str, Any]:
    datasets_tested = len(datasets)
    valid_datasets_count = sum(1 for row in datasets if row["valid"] is True)
    invalid_datasets_count = datasets_tested - valid_datasets_count
    average_net_pnl_percent = (
        sum(float(row["net_pnl_percent"]) for row in datasets) / datasets_tested
        if datasets_tested
        else 0.0
    )
    worst_drawdown = (
        max(float(row["max_drawdown"]) for row in datasets)
        if datasets
        else 0.0
    )
    robust = (
        datasets_tested >= 3
        and valid_datasets_count >= datasets_tested * 0.60
        and average_net_pnl_percent > 0
        and worst_drawdown <= 0.20
    )
    return {
        "datasets_tested": datasets_tested,
        "valid_datasets_count": valid_datasets_count,
        "invalid_datasets_count": invalid_datasets_count,
        "average_net_pnl_percent": average_net_pnl_percent,
        "worst_drawdown": worst_drawdown,
        "robust": robust,
    }


def _candidate_rejection_reason(candidate: dict[str, Any], robust: bool) -> str | None:
    if candidate.get("valid") is not True:
        return str(candidate.get("reason", "invalid strategy"))
    if int(candidate.get("number_of_trades", 0)) < 20:
        return "too few trades"
    if candidate.get("walk_forward_stable") is not True:
        return "walk-forward unstable"
    if not robust:
        return "strategy is not robust across datasets"
    return None


def _sharpe_like(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    volatility = pstdev(returns)
    if volatility == 0:
        return 0.0
    return mean(returns) / volatility * sqrt(len(returns))


if __name__ == "__main__":
    main()
