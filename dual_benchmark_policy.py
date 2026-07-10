from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DualBenchmarkPolicy:
    starting_balance: float = 10_000.0
    commission_percent: float = 0.1
    slippage_percent: float = 0.05
    spread_percent: float = 0.02
    latency_bars: int = 1
    reset_positions_between_segments: bool = True
    signal_timestamp_tolerance_bars: int = 0
    execution_timestamp_tolerance_bars: int = 1

    def to_dict(self) -> dict[str, float | bool | int]: return asdict(self)
