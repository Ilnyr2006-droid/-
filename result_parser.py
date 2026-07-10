from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FreqtradeTradeRecord:
    pair: str | None; open_date: str | None; close_date: str | None; open_rate: float | None; close_rate: float | None; amount: float | None; profit_abs: float | None; profit_ratio: float | None; exit_reason: str | None; is_open: bool | None

@dataclass(frozen=True)
class FreqtradeBacktestArtifact:
    source_path: str; source_sha256: str; strategy: str | None; timeframe: str | None; timerange: str | None; starting_balance: float | None; ending_balance: float | None; total_trades: int | None; closed_trades: int | None; open_trades: int | None; warnings: tuple[str, ...]


def parse_backtest_zip(path: str | Path) -> tuple[FreqtradeBacktestArtifact, list[FreqtradeTradeRecord]]:
    source = Path(path); warnings: list[str] = []
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names): raise ValueError("unsafe ZIP member")
        candidates = [name for name in names if name.endswith(".json") and not name.endswith("_config.json")]
        if len(candidates) != 1: raise ValueError("expected one backtest JSON")
        payload = json.loads(archive.read(candidates[0]))
    strategies = payload.get("strategy", {})
    if len(strategies) != 1: raise ValueError("expected one strategy result")
    name, result = next(iter(strategies.items())); trades = result.get("trades", [])
    if not isinstance(trades, list): warnings.append("trade list unavailable"); trades = []
    parsed = [FreqtradeTradeRecord(t.get("pair"), t.get("open_date"), t.get("close_date"), _float(t.get("open_rate")), _float(t.get("close_rate")), _float(t.get("amount")), _float(t.get("profit_abs")), _float(t.get("profit_ratio")), t.get("exit_reason"), t.get("is_open")) for t in trades]
    open_trades = sum(bool(t.is_open) for t in parsed)
    artifact = FreqtradeBacktestArtifact(str(source), hashlib.sha256(source.read_bytes()).hexdigest(), name, result.get("timeframe"), result.get("timerange"), _float(result.get("starting_balance")), _float(result.get("final_balance")), result.get("total_trades"), len(parsed)-open_trades if trades else None, open_trades if trades else None, tuple(warnings))
    return artifact, parsed


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None
