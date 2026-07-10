from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freqtrade_adapter.common_overlap import build_segments, save_manifest
from freqtrade_adapter.data_converter import read_freqtrade_dataset
from freqtrade_adapter.legacy_segment_runner import run_legacy_segment
from freqtrade_adapter.result_parser import parse_backtest_zip


METRIC_TOLERANCES = {
    "net_pnl": 0.05,
    "winrate": 0.05,
    "max_drawdown": 0.05,
    "fees": 0.05,
}


def compare_engines(legacy: dict[str, Any], freqtrade: dict[str, Any]) -> dict[str, Any]:
    """Compare already-exported results; this function never invokes either engine."""
    differences: dict[str, Any] = {}
    for metric, tolerance in METRIC_TOLERANCES.items():
        left = float(legacy.get(metric, 0.0))
        right = float(freqtrade.get(metric, 0.0))
        relative = abs(left - right) / max(abs(left), 1.0)
        differences[metric] = {"legacy": left, "freqtrade": right, "relative_difference": relative, "within_tolerance": relative <= tolerance}
    differences["trade_count"] = {"legacy": int(legacy.get("trade_count", 0)), "freqtrade": int(freqtrade.get("trade_count", 0))}
    differences["explanations_required"] = [
        key for key, value in differences.items() if isinstance(value, dict) and value.get("within_tolerance") is False
    ]
    return differences


def save_dual_engine_benchmark(strategy: str, legacy: dict[str, Any], freqtrade: dict[str, Any], results_dir: str | Path = "results") -> Path:
    output = Path(results_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output / f"freqtrade_dual_benchmark_{timestamp}.json"
    path.write_text(json.dumps({"strategy": strategy, "comparison": compare_engines(legacy, freqtrade), "tolerances": METRIC_TOLERANCES}, indent=2), encoding="utf-8")
    return path


def run_eligible_benchmark(eligibility: dict[str, Any], legacy_dir: str | Path, freqtrade_dir: str | Path, artifacts_dir: str | Path) -> tuple[dict[str, Any], Path]:
    combinations, blocked, segments_manifest = [], [], []
    for row in eligibility["combinations"]:
        if not row["allowed_for_trade_comparison"]:
            blocked.append({**row, "classification": "DATA_BLOCKED"}); continue
        legacy_path = Path(legacy_dir) / f"{row['symbol']}_{row['timeframe']}.csv"
        freq_path = next(Path(freqtrade_dir).rglob(f"{row['symbol'][:-4]}_USDT-{row['timeframe']}.feather"), None)
        if freq_path is None: combinations.append({**row, "classification": "ARTIFACT_MISSING", "blocker": "FREQTRADE_DATASET_MISSING"}); continue
        legacy_frame, legacy_info = read_freqtrade_dataset(legacy_path); freq_frame, freq_info = read_freqtrade_dataset(freq_path)
        segments = build_segments(legacy_frame, freq_frame, row["symbol"], row["timeframe"], 30, legacy_info.sha256_source, freq_info.sha256_source); segments_manifest.extend(segments)
        runs = [run_legacy_segment(legacy_frame[(legacy_frame.timestamp >= segment.start_timestamp) & (legacy_frame.timestamp <= segment.end_timestamp)], row["symbol"], row["strategy"]) for segment in segments if segment.eligible]
        combinations.append({**row, "segments": [segment.__dict__ for segment in segments], "legacy_runs": runs, "classification": "INSUFFICIENT_DATA", "blocker": "FREQTRADE_ARTIFACT_NOT_SEGMENT_TIMERANGE_MATCHED", "warnings": ["Existing Freqtrade exports cover provider ranges, not immutable common-overlap segments; no execution equivalence is claimed."]})
    segment_path = save_manifest(segments_manifest)
    report = {"run_config": {"legacy_dir": str(legacy_dir), "freqtrade_dir": str(freqtrade_dir), "artifacts_dir": str(artifacts_dir)}, "eligibility_source": eligibility.get("diagnosis_path"), "segments_manifest": str(segment_path), "combinations": combinations, "blocked_combinations": blocked, "summary": {"total": len(eligibility["combinations"]), "eligible": sum(row["allowed_for_trade_comparison"] for row in eligibility["combinations"]), "blocked": len(blocked), "executed": len(combinations), "equivalent": 0, "approximately_equivalent": 0, "signal_equivalent_execution_differs": 0, "non_equivalent": 0, "insufficient_data": len(combinations)}, "status": "NOT_READY"}
    output = Path("results") / f"freqtrade_dual_benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"; output.write_text(json.dumps(report, indent=2, default=str)); return report, output
