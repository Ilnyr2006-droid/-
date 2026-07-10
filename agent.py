from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from broker_paper import BrokerPaper
from backtest import (
    compare_strategies,
    compare_strategies_on_data_dir,
    format_backtest_report,
    format_candidate_selection_report,
    format_robustness_report,
    format_walk_forward_report,
    run_backtest_for_symbol,
    run_robustness,
    run_walk_forward,
    select_candidate,
    save_compare_result,
    save_backtest_result,
    sweep_ema_crossover,
)
from data_provider import DataProvider
from features import save_feature_report
from models import OrderSide, OrderStatus, Signal, TradeProposal
from order_gateway import OrderGateway
from paper_replay import format_paper_replay_report, load_frozen_replay_config, run_paper_replay
from reports import format_journal_report, generate_journal_report
from research_config import load_research_config
from research.strategy_attribution import run_strategy_attribution, save_strategy_attribution_report
from research.filter_sweep import run_filter_sweep, save_filter_sweep
from research.strategy_router import run_regime_strategy_report, save_regime_strategy_report
from research.regime_backtest import run_regime_router_backtest, save_regime_backtest_report
from research.regime_attribution import run_regime_attribution, save_regime_attribution_report
from research.trade_lifecycle import run_trade_lifecycle, save_trade_lifecycle_report
from research.exit_analysis import run_exit_analysis, save_exit_analysis_report
from research.position_management import run_position_management, save_position_management_report
from research.monte_carlo import run_monte_carlo, save_monte_carlo_report
from research.entry_quality import run_entry_quality, save_entry_quality_report
from research.signal_quality import run_signal_quality, save_signal_quality_report
from research.entry_timing import run_entry_timing, save_entry_timing_report
from research.regime_transition import run_regime_transition, save_regime_transition_report
from research.opportunity_analysis import run_opportunity_analysis, save_opportunity_analysis_report
from research.transition_entry import run_transition_entry_analysis, save_transition_entry_report
from research.trend_confirmation_delay import run_trend_confirmation_delay, save_trend_confirmation_delay_report
from research.exit_optimization import run_exit_optimization, save_exit_optimization_report
from research.entry_threshold import run_entry_threshold, save_entry_threshold_report
from research.multi_asset_validation import run_multi_asset_validation, save_multi_asset_validation_report
from research.portfolio_validation import run_portfolio_validation, save_portfolio_validation_report
from research.market_microstructure import run_market_microstructure, save_market_microstructure_report
from research.benchmark_suite import BENCHMARK_STRATEGIES, run_benchmark_suite
from freqtrade_adapter.data_comparison import compare_data_directories, save_comparison
from freqtrade_adapter.data_diagnosis import diagnose as diagnose_freqtrade_data
from freqtrade_adapter.dual_benchmark_eligibility import build_eligibility
from freqtrade_adapter.dual_engine_benchmark import run_eligible_benchmark
from risk_manager import RiskManager
from strategies import STRATEGY_REGISTRY
from strategy import EMACrossoverStrategy


@dataclass(frozen=True)
class AgentDecision:
    symbol: str
    signal: Signal
    approved: bool
    reason: str
    order_status: str | None


@dataclass(frozen=True)
class ReportOnlyResult:
    symbol: str
    signal: Signal
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_percent: float
    reason: str


class PaperTradingAgent:
    """Analysis agent. It proposes trades; RiskManager and BrokerPaper control execution."""

    def __init__(
        self,
        data_provider: DataProvider | None = None,
        strategy: EMACrossoverStrategy | None = None,
        risk_manager: RiskManager | None = None,
        broker: BrokerPaper | None = None,
        order_gateway: OrderGateway | None = None,
        journal_path: str | Path = "journal.jsonl",
    ) -> None:
        self.data_provider = data_provider or DataProvider()
        self.strategy = strategy or EMACrossoverStrategy()
        self.risk_manager = risk_manager or RiskManager()
        self.broker = broker or BrokerPaper()
        self.journal_path = Path(journal_path)
        self.order_gateway = order_gateway or OrderGateway(
            self.broker,
            self.risk_manager,
            self.journal_path,
        )

    def analyze_and_propose(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> AgentDecision:
        bars = self.data_provider.get_bars(symbol, timeframe, limit)
        signal = self.strategy.signal(bars)
        latest_price = bars[-1].close
        proposal = self._build_proposal(symbol, signal, latest_price)

        order_status: str | None = None
        if proposal is not None:
            order = self.order_gateway.execute(proposal)
            order_status = order.status.value
            approved = order.status == OrderStatus.FILLED
            reason = order.reason or "approved"
        else:
            decision = self.risk_manager.approve_trade(signal, self.broker.account_state(), proposal)
            approved = decision.approved
            reason = decision.reason

        agent_decision = AgentDecision(
            symbol=symbol,
            signal=signal,
            approved=approved,
            reason=reason,
            order_status=order_status,
        )
        self._log_decision(agent_decision, proposal)
        return agent_decision

    def report_only(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> ReportOnlyResult:
        bars = self.data_provider.get_bars(symbol, timeframe, limit)
        signal = self.strategy.signal(bars)
        latest_price = bars[-1].close
        proposal = self._build_proposal(symbol, signal, latest_price)
        account_state = self.broker.account_state()
        decision = self.risk_manager.approve_trade(signal, account_state, proposal)

        report = ReportOnlyResult(
            symbol=symbol,
            signal=signal,
            entry=proposal.price if proposal else latest_price,
            stop_loss=proposal.stop_loss if proposal else None,
            take_profit=proposal.take_profit if proposal else None,
            risk_percent=(
                proposal.risk_amount / account_state.equity * 100
                if proposal and account_state.equity > 0
                else 0.0
            ),
            reason=decision.reason,
        )
        self._log_report(report)
        return report

    def _build_proposal(
        self,
        symbol: str,
        signal: Signal,
        price: float,
    ) -> TradeProposal | None:
        if signal == Signal.HOLD:
            return None
        account = self.broker.account_state()
        if signal == Signal.BUY:
            quantity = (account.equity * 0.10) / price
            return TradeProposal(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                price=price,
                stop_loss=price * 0.99,
                take_profit=price * 1.02,
            )
        position = account.positions.get(symbol)
        if position is None:
            return None
        return TradeProposal(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            price=price,
            stop_loss=price * 1.01,
            take_profit=price * 0.98,
        )

    def _log_decision(
        self,
        decision: AgentDecision,
        proposal: TradeProposal | None,
    ) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": asdict(decision),
            "proposal": asdict(proposal) if proposal else None,
            "account": {
                "balance": self.broker.balance,
                "equity": self.broker.equity,
                "positions": {
                    symbol: asdict(position)
                    for symbol, position in self.broker.positions.items()
                },
            },
        }
        with self.journal_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _log_report(self, report: ReportOnlyResult) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "report_only",
            "report": asdict(report),
        }
        with self.journal_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    parser = ArgumentParser(description="Paper-only trading agent")
    parser.add_argument(
        "--mode",
        choices=(
            "paper",
            "report_only",
            "backtest",
            "report",
            "compare",
            "walk_forward",
            "sweep",
            "robustness",
            "select_candidate",
            "paper_replay",
            "feature_report",
            "strategy_report",
            "filter_sweep",
            "regime_report",
            "regime_backtest",
            "regime_attribution",
            "trade_lifecycle",
            "exit_analysis",
            "position_management",
            "monte_carlo",
            "entry_quality",
            "signal_quality",
            "entry_timing",
            "regime_transition",
            "opportunity_analysis",
            "transition_entry",
            "trend_confirmation_delay",
            "exit_optimization",
            "entry_threshold",
            "multi_asset_validation",
            "portfolio_validation",
            "market_microstructure",
            "benchmark_suite",
            "freqtrade_data_compare",
            "freqtrade_data_diagnose",
            "freqtrade_dual_benchmark",
        ),
        default="paper",
    )
    parser.add_argument("--symbol", default="MOCK")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--strategy", choices=tuple(STRATEGY_REGISTRY), default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--journal", default="journal.jsonl")
    parser.add_argument("--journal-path", default="journal.jsonl")
    parser.add_argument("--save-results", action="store_true")
    parser.add_argument("--save-selected-config", action="store_true")
    parser.add_argument("--train-size", type=int, default=120)
    parser.add_argument("--test-size", type=int, default=60)
    parser.add_argument("--data-source", choices=("mock", "csv"), default="mock")
    parser.add_argument("--csv-path")
    parser.add_argument("--data-dir", default="data/markets")
    parser.add_argument("--freqtrade-data-dir", default="freqtrade_user_data/data")
    parser.add_argument("--freqtrade-results-dir", default="freqtrade_user_data/backtest_results")
    parser.add_argument("--diagnosis")
    parser.add_argument("--eligibility")
    parser.add_argument("--config")
    parser.add_argument("--validation-mode", choices=("paper", "research"), default="paper")
    parser.add_argument("--opportunity-threshold", type=float, default=2.0)
    parser.add_argument("--benchmark-strategies")
    args = parser.parse_args()
    effective_strategy = args.strategy or "ema_crossover"
    data_dir_provided = "--data-dir" in sys.argv

    if args.mode == "freqtrade_data_compare":
        report = compare_data_directories(args.data_dir, args.freqtrade_data_dir)
        output_path = save_comparison(report)
        print(json.dumps({**report["summary"], "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "freqtrade_data_diagnose":
        report, output_path = diagnose_freqtrade_data(args.data_dir, args.freqtrade_data_dir)
        print(json.dumps({**report["summary"], "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "freqtrade_dual_benchmark":
        diagnosis = Path(args.diagnosis) if args.diagnosis else max(Path("results").glob("freqtrade_data_diagnosis_*.json"), key=lambda path: path.stat().st_mtime)
        if not Path(args.freqtrade_results_dir).is_dir():
            raise ValueError(f"Freqtrade backtest results directory not found: {args.freqtrade_results_dir}")
        if args.eligibility:
            eligibility = json.loads(Path(args.eligibility).read_text())
        else:
            eligibility, _ = build_eligibility(diagnosis)
        report, output_path = run_eligible_benchmark(eligibility, args.data_dir, args.freqtrade_data_dir, args.freqtrade_results_dir)
        print(json.dumps({**report["summary"], "output_path": str(output_path)}, indent=2))
        return

    if args.mode == "backtest":
        result = run_backtest_for_symbol(
            args.symbol,
            args.timeframe,
            max(args.limit, 300),
            strategy_name=effective_strategy,
            data_source=args.data_source,
            csv_path=args.csv_path,
            validation_mode=args.validation_mode,
        )
        if args.save_results:
            save_backtest_result(result)
        print(format_backtest_report(result))
        return
    if args.mode == "compare":
        limit = max(args.limit, 300)
        if data_dir_provided:
            result = compare_strategies_on_data_dir(
                data_dir=args.data_dir,
                limit=limit,
                validation_mode=args.validation_mode,
            )
            print(json.dumps(result, indent=2))
            return
        result = compare_strategies(
            args.symbol,
            args.timeframe,
            limit,
            data_source=args.data_source,
            csv_path=args.csv_path,
            validation_mode=args.validation_mode,
        )
        if args.save_results:
            save_compare_result(
                result,
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=limit,
                data_source=args.data_source,
                csv_path=args.csv_path,
            )
        print(json.dumps(result, indent=2))
        return
    if args.mode == "sweep":
        if effective_strategy != "ema_crossover":
            raise ValueError("sweep mode currently supports only ema_crossover")
        result = sweep_ema_crossover(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
            data_source=args.data_source,
            csv_path=args.csv_path,
        )
        print(json.dumps(result, indent=2))
        return
    if args.mode == "robustness":
        result = run_robustness(
            strategy_name=effective_strategy,
            data_dir=args.data_dir,
            limit=max(args.limit, 300),
            validation_mode=args.validation_mode,
        )
        print(format_robustness_report(result))
        return
    if args.mode == "select_candidate":
        result = select_candidate(
            data_dir=args.data_dir,
            strategy_name=args.strategy or "all",
            limit=max(args.limit, 300),
            save_selected_config=args.save_selected_config,
            validation_mode=args.validation_mode,
        )
        print(format_candidate_selection_report(result))
        return
    if args.mode == "paper_replay":
        if args.config is None:
            raise ValueError("paper_replay requires --config config/selected_candidate.json")
        if args.strategy is not None:
            raise ValueError("cannot override --strategy when --config is provided")
        if args.csv_path is None:
            raise ValueError("paper_replay requires --csv-path")
        frozen_config = load_frozen_replay_config(args.config, args.csv_path)
        result = run_paper_replay(
            symbol=args.symbol,
            csv_path=args.csv_path,
            strategy_name=frozen_config.strategy,
            strategy_params=frozen_config.params,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
            journal_path="journal_replay.jsonl",
            config_path=frozen_config.config_path,
            config_selected_at=frozen_config.selected_at,
            warning=frozen_config.warning,
        )
        print(format_paper_replay_report(result))
        return
    if args.mode == "feature_report":
        if args.csv_path is None:
            raise ValueError("feature_report requires --csv-path with historical CSV candles")
        bars = DataProvider().get_bars(
            args.symbol,
            args.timeframe,
            max(args.limit, 200),
            data_source="csv",
            csv_path=args.csv_path,
        )
        report, output_path = save_feature_report(
            args.symbol,
            args.timeframe,
            args.csv_path,
            bars,
        )
        print(json.dumps({**report, "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "strategy_report":
        if args.csv_path is None:
            raise ValueError("strategy_report requires --csv-path with historical CSV candles")
        report = run_strategy_attribution(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
            csv_path=args.csv_path,
            strategy_name=effective_strategy,
        )
        output_path = save_strategy_attribution_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "filter_sweep":
        if args.csv_path is None:
            raise ValueError("filter_sweep requires --csv-path with historical CSV candles")
        results = run_filter_sweep(
            strategy=effective_strategy,
            symbol=args.symbol,
            csv_path=args.csv_path,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
        )
        output_path = save_filter_sweep(results, effective_strategy, args.symbol, args.timeframe)
        print(json.dumps({"results": [asdict(result) for result in results], "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "regime_report":
        if args.csv_path is None:
            raise ValueError("regime_report requires --csv-path with historical CSV candles")
        report = run_regime_strategy_report(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
            csv_path=args.csv_path,
        )
        output_path = save_regime_strategy_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "regime_backtest":
        if args.csv_path is None:
            raise ValueError("regime_backtest requires --csv-path with historical CSV candles")
        report = run_regime_router_backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=max(args.limit, 300),
            csv_path=args.csv_path,
        )
        output_path = save_regime_backtest_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "regime_attribution":
        report = run_regime_attribution(args.journal)
        output_path = save_regime_attribution_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "trade_lifecycle":
        report = run_trade_lifecycle(args.journal)
        output_path = save_trade_lifecycle_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "exit_analysis":
        report = run_exit_analysis(args.journal)
        output_path = save_exit_analysis_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "position_management":
        results = run_position_management(args.journal)
        output_path = save_position_management_report(results, args.journal)
        print(json.dumps({"results": [asdict(result) for result in results], "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "monte_carlo":
        report = run_monte_carlo(args.journal)
        output_path = save_monte_carlo_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "entry_quality":
        report = run_entry_quality(args.journal)
        output_path = save_entry_quality_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "signal_quality":
        report = run_signal_quality(args.journal)
        output_path = save_signal_quality_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "entry_timing":
        report = run_entry_timing(args.journal)
        output_path = save_entry_timing_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "regime_transition":
        report = run_regime_transition(args.journal)
        output_path = save_regime_transition_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "opportunity_analysis":
        if args.csv_path is None:
            raise ValueError("opportunity_analysis requires --csv-path with historical CSV candles")
        report = run_opportunity_analysis(
            symbol=args.symbol,
            csv_path=args.csv_path,
            timeframe=args.timeframe,
            limit=max(args.limit, 100),
            threshold_percent=args.opportunity_threshold,
        )
        output_path = save_opportunity_analysis_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "transition_entry":
        report = run_transition_entry_analysis(args.journal)
        output_path = save_transition_entry_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "trend_confirmation_delay":
        journal = args.journal if "--journal" in sys.argv else None
        report = run_trend_confirmation_delay(journal)
        output_path = save_trend_confirmation_delay_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "exit_optimization":
        report = run_exit_optimization(args.journal)
        output_path = save_exit_optimization_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "entry_threshold":
        report = run_entry_threshold(args.journal)
        output_path = save_entry_threshold_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "multi_asset_validation":
        report = run_multi_asset_validation(args.data_dir, limit=max(args.limit, 90))
        output_path = save_multi_asset_validation_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "portfolio_validation":
        report = run_portfolio_validation(args.data_dir, limit=max(args.limit, 90))
        output_path = save_portfolio_validation_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "market_microstructure":
        if args.csv_path is None:
            raise ValueError("market_microstructure requires --csv-path with historical CSV candles")
        report = run_market_microstructure(
            symbol=args.symbol,
            csv_path=args.csv_path,
            timeframe=args.timeframe,
            limit=max(args.limit, 100),
        )
        output_path = save_market_microstructure_report(report)
        print(json.dumps({**asdict(report), "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "benchmark_suite":
        strategies = (
            tuple(args.benchmark_strategies.split(","))
            if args.benchmark_strategies
            else BENCHMARK_STRATEGIES
        )
        report, output_path = run_benchmark_suite(args.data_dir, strategies)
        print(json.dumps({**report, "output_path": str(output_path)}, indent=2))
        return
    if args.mode == "walk_forward":
        research_config = load_research_config() if args.validation_mode == "research" else None
        train_size = (
            research_config.walk_forward_train_size
            if research_config is not None
            else args.train_size
        )
        test_size = (
            research_config.walk_forward_test_size
            if research_config is not None
            else args.test_size
        )
        if data_dir_provided:
            directory = Path(args.data_dir)
            csv_files = sorted(directory.glob("*.csv")) if directory.is_dir() else []
            if not csv_files:
                raise ValueError(f"no CSV datasets found in data_dir: {directory}")
            reports = []
            for csv_file in csv_files:
                parts = csv_file.stem.rsplit("_", 1)
                if len(parts) != 2:
                    raise ValueError(f"dataset name must be SYMBOL_TIMEFRAME.csv: {csv_file.name}")
                symbol, timeframe = parts
                reports.append(
                    asdict(
                        run_walk_forward(
                            symbol=symbol,
                            strategy_name=effective_strategy,
                            timeframe=timeframe,
                            limit=max(args.limit, train_size + test_size),
                            train_size=train_size,
                            test_size=test_size,
                            data_source="csv",
                            csv_path=csv_file,
                            validation_mode=args.validation_mode,
                            research_config=research_config,
                        )
                    )
                )
            print(json.dumps(reports, indent=2))
            return

        result = run_walk_forward(
            symbol=args.symbol,
            strategy_name=effective_strategy,
            timeframe=args.timeframe,
            limit=max(args.limit, train_size + test_size),
            train_size=train_size,
            test_size=test_size,
            data_source=args.data_source,
            csv_path=args.csv_path,
            validation_mode=args.validation_mode,
            research_config=research_config,
        )
        print(format_walk_forward_report(result))
        return
    if args.mode == "report":
        print(format_journal_report(generate_journal_report(args.journal)))
        return

    agent = PaperTradingAgent(journal_path=args.journal_path)
    if args.mode == "report_only":
        result = agent.report_only(args.symbol, args.timeframe, args.limit)
    else:
        result = agent.analyze_and_propose(args.symbol, args.timeframe, args.limit)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
