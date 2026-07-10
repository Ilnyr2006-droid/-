from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from tools.download_data import TIMEFRAME_TO_MILLISECONDS
from tools.audit_market_data import audit_csv


CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class FreqtradeDatasetInfo:
    source_path: str
    source_format: str
    symbol: str
    timeframe: str
    rows: int
    start_timestamp: str | None
    end_timestamp: str | None
    duplicate_count: int
    conflicting_duplicate_count: int
    gap_count: int
    invalid_ohlc_count: int
    sha256_source: str
    sha256_normalized: str
    valid: bool
    warnings: tuple[str, ...]


def read_freqtrade_ohlcv(path: str | Path) -> list[dict[str, str]]:
    frame, _ = read_freqtrade_dataset(path)
    return [
        {"timestamp": row.timestamp.isoformat(), **{column: str(getattr(row, column)) for column in CSV_COLUMNS[1:]}}
        for row in frame.itertuples(index=False)
    ]


def read_freqtrade_dataset(path: str | Path) -> tuple[pd.DataFrame, FreqtradeDatasetInfo]:
    source = Path(path)
    raw = _read_source(source)
    frame = _normalise(raw)
    symbol, timeframe = _name_parts(source)
    duplicate_count, conflicting_count = _duplicate_counts(frame)
    frame = frame.drop_duplicates(subset=["timestamp"], keep="first").sort_values("timestamp").reset_index(drop=True)
    invalid = int(((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1)) | (frame[list(CSV_COLUMNS[1:])] <= 0).any(axis=1)).sum())
    gap_count = _gap_count(frame["timestamp"], timeframe)
    warnings: list[str] = []
    if conflicting_count:
        warnings.append("conflicting duplicate timestamps detected")
    if gap_count:
        warnings.append("missing candle intervals detected")
    if invalid:
        warnings.append("invalid OHLCV rows detected")
    info = FreqtradeDatasetInfo(
        source_path=str(source), source_format=_format(source), symbol=symbol, timeframe=timeframe,
        rows=len(frame), start_timestamp=_iso(frame["timestamp"].min() if len(frame) else None),
        end_timestamp=_iso(frame["timestamp"].max() if len(frame) else None), duplicate_count=duplicate_count,
        conflicting_duplicate_count=conflicting_count, gap_count=gap_count, invalid_ohlc_count=invalid,
        sha256_source=_sha256(source), sha256_normalized=_normalised_sha(frame),
        valid=bool(len(frame)) and not conflicting_count and not invalid, warnings=tuple(warnings),
    )
    return frame, info


def export_csv(rows: list[dict[str, str]], output: str | Path) -> dict[str, Any]:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    return audit_csv(path)


def dataset_info_dict(path: str | Path) -> dict[str, Any]:
    _, info = read_freqtrade_dataset(path)
    return asdict(info)


def compare_csv_datasets(freqtrade_csv: str | Path, current_csv: str | Path) -> dict[str, Any]:
    left, left_info = read_freqtrade_dataset(freqtrade_csv)
    right, right_info = read_freqtrade_dataset(current_csv)
    return {"freqtrade": asdict(left_info), "current": asdict(right_info), "row_count_difference": len(left) - len(right), "same_sha256": left_info.sha256_normalized == right_info.sha256_normalized}


def _read_source(source: Path) -> pd.DataFrame:
    suffixes = "".join(source.suffixes).lower()
    if suffixes.endswith(".feather"): return pd.read_feather(source)
    if suffixes.endswith(".parquet"): return pd.read_parquet(source)
    if suffixes.endswith(".csv"): return pd.read_csv(source)
    opener = gzip.open if suffixes.endswith(".gz") else open
    with opener(source, "rt", encoding="utf-8") as file: payload = json.load(file)
    if not isinstance(payload, list): raise ValueError("Freqtrade OHLCV must be a list")
    return pd.DataFrame(payload, columns=["timestamp", "open", "high", "low", "close", "volume"])


def _normalise(raw: pd.DataFrame) -> pd.DataFrame:
    timestamp = "date" if "date" in raw.columns else "timestamp"
    if timestamp not in raw or not set(CSV_COLUMNS[1:]).issubset(raw.columns): raise ValueError("missing OHLCV columns")
    frame = raw[[timestamp, *CSV_COLUMNS[1:]]].rename(columns={timestamp: "timestamp"}).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    for column in CSV_COLUMNS[1:]: frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.isna().any().any(): raise ValueError("OHLCV data contains invalid timestamp or NaN")
    return frame


def _duplicate_counts(frame: pd.DataFrame) -> tuple[int, int]:
    duplicates = frame[frame.duplicated("timestamp", keep=False)]
    if duplicates.empty: return 0, 0
    conflicts = sum(group[list(CSV_COLUMNS[1:])].drop_duplicates().shape[0] > 1 for _, group in duplicates.groupby("timestamp"))
    return int(duplicates.duplicated("timestamp").sum()), int(conflicts)


def _gap_count(timestamps: pd.Series, timeframe: str) -> int:
    interval = TIMEFRAME_TO_MILLISECONDS.get(timeframe)
    if interval is None or len(timestamps) < 2: return 0
    deltas = timestamps.sort_values().diff().dropna().dt.total_seconds() * 1000
    return int(sum(max(0, round(delta / interval) - 1) for delta in deltas if delta > interval))


def _name_parts(path: Path) -> tuple[str, str]:
    stem = path.name.split(".")[0].replace("-", "_")
    if "_" not in stem: return stem, "unknown"
    symbol, timeframe = stem.rsplit("_", 1)
    return symbol.replace("_", ""), timeframe


def _format(path: Path) -> str: return "json.gz" if path.suffixes[-2:] == [".json", ".gz"] else path.suffix.lstrip(".")
def _iso(value: Any) -> str | None: return value.isoformat() if value is not None and not pd.isna(value) else None
def _sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _normalised_sha(frame: pd.DataFrame) -> str: return hashlib.sha256(frame.to_csv(index=False, date_format="iso").encode()).hexdigest()
