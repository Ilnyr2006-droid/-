from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from tools.download_data import TIMEFRAME_TO_MILLISECONDS


@dataclass(frozen=True)
class CommonOverlapSegment:
    segment_id: str; symbol: str; timeframe: str; start_timestamp: str; end_timestamp: str; rows_total: int; warmup_rows: int; usable_rows: int; gap_before: bool; gap_after: bool; legacy_source_hash: str; freqtrade_source_hash: str; eligible: bool; exclusion_reason: str | None; warnings: tuple[str, ...]


def build_segments(legacy: pd.DataFrame, freqtrade: pd.DataFrame, symbol: str, timeframe: str, startup: int, legacy_hash: str, freqtrade_hash: str) -> list[CommonOverlapSegment]:
    common = legacy.merge(freqtrade[["timestamp"]], on="timestamp")
    if len(common) and common["timestamp"].max() == freqtrade["timestamp"].max(): common = common.iloc[:-1]  # final candle is excluded only when shared
    interval = pd.Timedelta(milliseconds=TIMEFRAME_TO_MILLISECONDS[timeframe]); groups = []; current = []
    for timestamp in common["timestamp"].sort_values():
        if current and timestamp - current[-1] != interval: groups.append(current); current = []
        current.append(timestamp)
    if current: groups.append(current)
    output = []
    for index, group in enumerate(groups):
        usable = max(0, len(group) - startup); eligible = usable >= 2
        output.append(CommonOverlapSegment(f"{symbol}_{timeframe}_{index}", symbol, timeframe, group[0].isoformat(), group[-1].isoformat(), len(group), startup, usable, index > 0, index < len(groups)-1, legacy_hash, freqtrade_hash, eligible, None if eligible else "INSUFFICIENT_POST_WARMUP_CANDLES", ("FINAL_CANDLE_EXCLUDED",) if index == len(groups)-1 else ()))
    return output


def save_manifest(segments: list[CommonOverlapSegment], path: str | Path = "results") -> Path:
    target = Path(path) / f"freqtrade_common_overlap_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"; target.write_text(json.dumps([asdict(segment) for segment in segments], indent=2)); return target
