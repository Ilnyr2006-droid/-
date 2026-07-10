from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from backtest import run_backtest
from execution_model import ExecutionConfig
from models import Bar


def run_legacy_segment(frame: pd.DataFrame, symbol: str, strategy: str, starting_balance: float = 10_000.0) -> dict[str, Any]:
    bars = [Bar(timestamp=row.timestamp.to_pydatetime(), open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close), volume=float(row.volume)) for row in frame.itertuples(index=False)]
    result = run_backtest(bars, symbol, starting_balance=starting_balance, strategy_name=strategy, execution_config=ExecutionConfig(), journal_path=None)
    return {"signals": [], "entries": [trade.get("entry_time") for trade in result.trades], "exits": [trade.get("exit_time") for trade in result.trades], "trades": result.trades, "metrics": {"net_pnl": result.net_pnl, "net_pnl_percent": result.net_pnl_percent, "total_trades": result.number_of_trades, "max_drawdown": result.max_drawdown, "ending_balance": result.ending_balance, "fees": result.total_commission_paid}, "execution_assumptions": asdict(ExecutionConfig()), "warnings": ["Signal extraction is unavailable from the legacy execution engine; execution comparison remains separate."]}
