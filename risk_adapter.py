from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RiskAdapterStatus:
    max_risk_per_trade_pct: float
    max_position_pct: float
    max_open_trades: int
    stop_loss_required: bool
    spot_only: bool
    no_short: bool
    dry_run_promotion_blocked: bool
    gaps: list[str]


def assess_risk_adapter() -> RiskAdapterStatus:
    gaps = [
        "Freqtrade fixed stake and stoploss callbacks do not prove equivalent 1% per-trade risk for every fill.",
        "Daily cumulative loss guard is not equivalent to the current RiskManager daily-loss calculation.",
        "Consecutive-loss and portfolio drawdown protections require separate verified callback behavior.",
    ]
    return RiskAdapterStatus(1.0, 10.0, 1, True, True, True, True, gaps)


def write_risk_gaps(path: str | Path = "FREQTRADE_RISK_GAPS.md") -> Path:
    status = assess_risk_adapter()
    output = Path(path)
    lines = ["# Freqtrade Risk Gaps", "", "Dry-run promotion is blocked until every gap is verified.", ""]
    lines.extend(f"- {gap}" for gap in status.gaps)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def risk_adapter_payload() -> dict[str, object]:
    return asdict(assess_risk_adapter())
