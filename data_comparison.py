from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from freqtrade_adapter.data_converter import read_freqtrade_dataset


def compare_data_directories(legacy_dir: str | Path, freqtrade_dir: str | Path, tolerance: float = 1e-8) -> dict[str, Any]:
    legacy_files = {path.stem: path for path in Path(legacy_dir).glob("*.csv")}
    sources = [*Path(freqtrade_dir).rglob("*.feather"), *Path(freqtrade_dir).rglob("*.json"), *Path(freqtrade_dir).rglob("*.json.gz"), *Path(freqtrade_dir).rglob("*.parquet")]
    results, errors = [], []
    for source in sorted(sources):
        try:
            frame, info = read_freqtrade_dataset(source)
            key = f"{info.symbol}_{info.timeframe}"
            legacy_path = legacy_files.get(key)
            if legacy_path is None:
                errors.append({"source": str(source), "error": f"legacy dataset missing: {key}"}); continue
            legacy, legacy_info = read_freqtrade_dataset(legacy_path)
            results.append(compare_frames(key, legacy, frame, legacy_info.gap_count, info.gap_count, tolerance))
        except Exception as exc:
            errors.append({"source": str(source), "error": str(exc)})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "datasets": results, "errors": errors,
            "summary": {"compared": len(results), "compatible": sum(row["compatible"] for row in results), "critical_mismatches": sum(row["critical_mismatch"] for row in results)}}


def compare_frames(key: str, legacy: pd.DataFrame, freqtrade: pd.DataFrame, legacy_gaps: int, freqtrade_gaps: int, tolerance: float) -> dict[str, Any]:
    merged = legacy.merge(freqtrade, on="timestamp", how="inner", suffixes=("_legacy", "_freqtrade"))
    ohlc = ["open", "high", "low", "close"]
    close_delta = (merged["close_legacy"] - merged["close_freqtrade"]).abs() if len(merged) else pd.Series(dtype=float)
    ohlc_match = pd.Series(True, index=merged.index)
    for column in ohlc: ohlc_match &= (merged[f"{column}_legacy"] - merged[f"{column}_freqtrade"]).abs() <= tolerance
    volume_delta = (merged["volume_legacy"] - merged["volume_freqtrade"]).abs() if len(merged) else pd.Series(dtype=float)
    warnings = []
    if len(legacy) != len(freqtrade): warnings.append("row count differs")
    if not ohlc_match.all(): warnings.append("OHLC differs on common timestamps")
    critical = bool((~ohlc_match).any() or legacy_gaps or freqtrade_gaps)
    return {"dataset": key, "legacy_rows": len(legacy), "freqtrade_rows": len(freqtrade), "common_timestamps": len(merged),
            "missing_in_legacy": len(freqtrade) - len(merged), "missing_in_freqtrade": len(legacy) - len(merged),
            "ohlc_exact_matches": int(ohlc_match.sum()), "ohlc_differences_count": int((~ohlc_match).sum()),
            "average_absolute_close_difference": float(close_delta.mean()) if len(close_delta) else None,
            "maximum_close_difference": float(close_delta.max()) if len(close_delta) else None,
            "volume_difference": {"average_absolute": float(volume_delta.mean()) if len(volume_delta) else None, "maximum_absolute": float(volume_delta.max()) if len(volume_delta) else None},
            "duplicate_counts": {"legacy": int(legacy.duplicated("timestamp").sum()), "freqtrade": int(freqtrade.duplicated("timestamp").sum())},
            "gap_counts": {"legacy": legacy_gaps, "freqtrade": freqtrade_gaps}, "common_date_range": {"start": merged["timestamp"].min().isoformat() if len(merged) else None, "end": merged["timestamp"].max().isoformat() if len(merged) else None},
            "compatible": not critical, "critical_mismatch": critical, "warnings": warnings}


def save_comparison(report: dict[str, Any], directory: str | Path = "results") -> Path:
    path = Path(directory) / f"freqtrade_data_comparison_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
