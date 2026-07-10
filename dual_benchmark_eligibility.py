from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STRATEGIES = {"ema_crossover": {"freqtrade": "EmaCrossoverStrategy", "uses_volume": True, "uses_regime": False, "uses_atr": True}, "rsi_mean_reversion": {"freqtrade": "RsiMeanReversionStrategy", "uses_volume": True, "uses_regime": True, "uses_atr": False}, "breakout": {"freqtrade": "BreakoutStrategy", "uses_volume": True, "uses_regime": True, "uses_atr": True}}


def build_eligibility(diagnosis_path: str | Path, results_dir: str | Path = "results") -> tuple[dict[str, Any], Path]:
    diagnosis = json.loads(Path(diagnosis_path).read_text()); rows = []
    for dataset in diagnosis["datasets"]:
        symbol, timeframe = dataset["dataset"].rsplit("_", 1)
        for legacy, meta in STRATEGIES.items():
            volume_blocked = meta["uses_volume"] and not dataset["volume"]["exact_match"]
            eligible_data = dataset["status"] in {"EXACT_COMPATIBLE", "COVERAGE_DIFFERS_ONLY"}
            blocker = "VOLUME_INCOMPATIBLE" if volume_blocked else "GAP_SEGMENT_POLICY_REQUIRED" if dataset["gaps"]["freqtrade"] else None
            rows.append({"symbol": symbol, "timeframe": timeframe, "strategy": legacy, "freqtrade_strategy": meta["freqtrade"], "data_status": dataset["status"], "price_compatible": dataset["status"] in {"EXACT_COMPATIBLE", "COVERAGE_DIFFERS_ONLY"}, "volume_compatible": dataset["volume"]["exact_match"], "coverage_difference": dataset["status"] == "COVERAGE_DIFFERS_ONLY", "gap_count": dataset["gaps"]["freqtrade"], "partial_final_candle": dataset["status"] == "PRICE_INCOMPATIBLE", "strategy_uses_volume": meta["uses_volume"], "strategy_uses_regime": meta["uses_regime"], "strategy_uses_ATR": meta["uses_atr"], "allowed_for_signal_comparison": bool(eligible_data and not blocker), "allowed_for_trade_comparison": bool(eligible_data and not blocker), "blocker": blocker or "PRICE_OR_FINAL_CANDLE_INCOMPATIBLE", "warnings": dataset["warnings"]})
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "diagnosis_path": str(diagnosis_path), "combinations": rows, "summary": {"total": len(rows), "allowed": sum(row["allowed_for_signal_comparison"] for row in rows), "blocked": sum(not row["allowed_for_signal_comparison"] for row in rows)}}
    path = Path(results_dir) / f"freqtrade_dual_eligibility_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"; path.write_text(json.dumps(report, indent=2)); return report, path
