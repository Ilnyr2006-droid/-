from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from freqtrade_adapter.data_converter import read_freqtrade_dataset


PRICE_ABS_TOLERANCE = 1e-8
PRICE_REL_TOLERANCE = 1e-10


def diagnose(legacy_dir: str | Path, freqtrade_dir: str | Path, results_dir: str | Path = "results") -> tuple[dict[str, Any], Path]:
    legacy = {path.stem: path for path in Path(legacy_dir).glob("*.csv")}
    sources = sorted(Path(freqtrade_dir).rglob("*.feather"))
    root = Path(results_dir); aligned_dir = root / "aligned_datasets"; aligned_dir.mkdir(parents=True, exist_ok=True)
    rows, examples, provenance = [], {}, []
    for source in sources:
        frame, info = read_freqtrade_dataset(source); key = f"{info.symbol}_{info.timeframe}"; legacy_path = legacy.get(key)
        provenance.append(_provenance("freqtrade", source, info.symbol, info.timeframe, info.start_timestamp, info.end_timestamp))
        if legacy_path is None:
            rows.append({"dataset": key, "status": "INVALID_DATASET", "blocker": "legacy dataset missing"}); continue
        legacy_frame, legacy_info = read_freqtrade_dataset(legacy_path)
        provenance.append(_provenance("legacy", legacy_path, info.symbol, info.timeframe, legacy_info.start_timestamp, legacy_info.end_timestamp))
        report, aligned, sample = _compare(key, legacy_frame, frame, legacy_info.gap_count, info.gap_count)
        rows.append(report); examples[key] = sample
        (aligned_dir / f"{key}_overlap.json").write_text(json.dumps({"dataset": key, "legacy_sha256": legacy_info.sha256_source, "freqtrade_sha256": info.sha256_source, "rows": aligned}, indent=2), encoding="utf-8")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    prov_path = root / f"data_provenance_{timestamp}.json"; prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    example_path = root / f"freqtrade_data_mismatch_examples_{timestamp}.json"; example_path.write_text(json.dumps(examples, indent=2), encoding="utf-8")
    summary = {"datasets_tested": len(rows), "exact_compatible": sum(r.get("status") == "EXACT_COMPATIBLE" for r in rows), "price_compatible": sum(r.get("status") in {"EXACT_COMPATIBLE", "COVERAGE_DIFFERS_ONLY", "PRICE_COMPATIBLE_VOLUME_DIFFERS"} for r in rows), "timestamp_shift_suspected": sum(r.get("status") == "TIMESTAMP_SHIFT_SUSPECTED" for r in rows), "price_incompatible": sum(r.get("status") == "PRICE_INCOMPATIBLE" for r in rows)}
    diagnosis = {"generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "datasets": rows, "provenance_path": str(prov_path), "examples_path": str(example_path), "aligned_dir": str(aligned_dir)}
    output = root / f"freqtrade_data_diagnosis_{timestamp}.json"; output.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
    return diagnosis, output


def _compare(key: str, legacy: pd.DataFrame, freqtrade: pd.DataFrame, legacy_gaps: int, freqtrade_gaps: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    merged = legacy.merge(freqtrade, on="timestamp", suffixes=("_legacy", "_freqtrade"))
    fields, price_matches = ("open", "high", "low", "close"), pd.Series(True, index=merged.index)
    field_stats: dict[str, Any] = {}
    for field in fields:
        delta = (merged[f"{field}_legacy"] - merged[f"{field}_freqtrade"]).abs(); relative = delta / merged[f"{field}_legacy"].abs().clip(lower=1e-12)
        exact = delta == 0; tolerant = (delta <= PRICE_ABS_TOLERANCE) | (relative <= PRICE_REL_TOLERANCE); price_matches &= tolerant
        field_stats[field] = {"exact_match_count": int(exact.sum()), "tolerance_match_count": int(tolerant.sum()), "mismatch_count": int((~tolerant).sum()), "mismatch_percent": float((~tolerant).mean() * 100) if len(merged) else None, "mean_absolute_difference": float(delta.mean()) if len(delta) else None, "median_absolute_difference": float(delta.median()) if len(delta) else None, "max_absolute_difference": float(delta.max()) if len(delta) else None, "mean_relative_difference": float(relative.mean()) if len(relative) else None, "max_relative_difference": float(relative.max()) if len(relative) else None}
    vol = (merged["volume_legacy"] - merged["volume_freqtrade"]).abs(); volume_equal = bool((vol <= PRICE_ABS_TOLERANCE).all())
    shift_scores = {offset: _shift_score(legacy, freqtrade, offset) for offset in (-1, 0, 1)}
    best_offset = max(shift_scores, key=shift_scores.get)
    coverage_only = bool(price_matches.all()) and volume_equal
    if best_offset != 0 and shift_scores[best_offset] > shift_scores[0] + 0.2: status = "TIMESTAMP_SHIFT_SUSPECTED"
    elif not bool(price_matches.all()): status = "PRICE_INCOMPATIBLE"
    elif coverage_only and (len(legacy) != len(freqtrade) or legacy_gaps or freqtrade_gaps): status = "COVERAGE_DIFFERS_ONLY"
    elif bool(price_matches.all()) and not volume_equal: status = "PRICE_COMPATIBLE_VOLUME_DIFFERS"
    elif bool(price_matches.all()) and legacy_gaps == 0 and freqtrade_gaps == 0: status = "EXACT_COMPATIBLE"
    else: status = "SOURCE_INCOMPATIBLE"
    samples = []
    for _, row in merged.loc[~price_matches].head(20).iterrows():
        samples.append({"timestamp": row.timestamp.isoformat(), "legacy": {field: row[f"{field}_legacy"] for field in (*fields, "volume")}, "freqtrade": {field: row[f"{field}_freqtrade"] for field in (*fields, "volume")}, "suspected_reason": "FINAL_CANDLE_MAY_BE_OPEN" if row.timestamp == merged.timestamp.max() else "OHLC_VALUE_MISMATCH"})
    aligned = [{"timestamp": row.timestamp.isoformat(), "legacy": {field: float(row[f"{field}_legacy"]) for field in (*fields, "volume")}, "freqtrade": {field: float(row[f"{field}_freqtrade"]) for field in (*fields, "volume")}, "price_match": bool(match)} for (_, row), match in zip(merged.iterrows(), price_matches)]
    warnings = []
    if legacy_gaps or freqtrade_gaps: warnings.append("GAP_DIFFERENCE")
    if not volume_equal: warnings.append("volume-dependent strategies remain blocked")
    report = {"dataset": key, "status": status, "coverage": {"legacy_start": _iso(legacy.timestamp.min()), "legacy_end": _iso(legacy.timestamp.max()), "freqtrade_start": _iso(freqtrade.timestamp.min()), "freqtrade_end": _iso(freqtrade.timestamp.max()), "overlap_start": _iso(merged.timestamp.min()), "overlap_end": _iso(merged.timestamp.max()), "common_timestamps": len(merged), "legacy_outside_overlap": len(legacy)-len(merged), "freqtrade_outside_overlap": len(freqtrade)-len(merged)}, "price": field_stats, "volume": {"exact_match": volume_equal, "mean_absolute_difference": float(vol.mean()) if len(vol) else None, "max_absolute_difference": float(vol.max()) if len(vol) else None}, "gaps": {"legacy": legacy_gaps, "freqtrade": freqtrade_gaps}, "timestamp_offsets": shift_scores, "suspected_timestamp_shift": best_offset if best_offset else None, "allowed_for_signal_comparison": status in {"EXACT_COMPATIBLE", "COVERAGE_DIFFERS_ONLY"}, "allowed_for_trade_comparison": status in {"EXACT_COMPATIBLE", "COVERAGE_DIFFERS_ONLY"}, "warnings": warnings}
    return report, aligned, samples


def _shift_score(left: pd.DataFrame, right: pd.DataFrame, bars: int) -> float:
    shifted = right.copy(); shifted["timestamp"] += pd.Timedelta(hours=bars)  # overwritten below by inferred cadence
    if len(right) > 1: shifted["timestamp"] = right["timestamp"] + (right["timestamp"].sort_values().diff().median() * bars)
    joined = left.merge(shifted, on="timestamp", suffixes=("_l", "_r")); return float(((joined["close_l"] - joined["close_r"]).abs() <= PRICE_ABS_TOLERANCE).mean()) if len(joined) else 0.0


def _provenance(provider: str, path: Path, symbol: str, timeframe: str, start: str | None, end: str | None) -> dict[str, Any]:
    return {"provider": provider, "exchange": "binance" if provider == "freqtrade" else "legacy downloader", "market_type": "spot", "symbol": symbol, "timeframe": timeframe, "timestamp_semantics": "UTC candle open", "timezone": "UTC", "start": start, "end": end, "source_path": str(path), "source_artifact_hash": hashlib.sha256(path.read_bytes()).hexdigest(), "warnings": ["last candle may be open"]}


def _iso(value: Any) -> str | None: return value.isoformat() if value is not None and not pd.isna(value) else None
