from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from math import isfinite, sin
from pathlib import Path

from models import Bar


class DataProvider:
    """OHLCV provider with deterministic mock data and local CSV support."""

    def __init__(self, mock_bars: dict[str, list[Bar]] | None = None) -> None:
        self._mock_bars = mock_bars or {}

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        data_source: str = "mock",
        csv_path: str | Path | None = None,
    ) -> list[Bar]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if timeframe not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            raise ValueError(f"unsupported timeframe: {timeframe}")

        normalized_source = data_source.lower()
        if normalized_source == "csv":
            if csv_path is None:
                raise ValueError("csv_path is required when data_source=csv")
            bars = self._load_csv_bars(Path(csv_path))
            return bars[-limit:] if len(bars) > limit else bars
        if normalized_source != "mock":
            raise ValueError("unsupported data_source: expected 'mock' or 'csv'")

        if symbol in self._mock_bars:
            return self._mock_bars[symbol][-limit:]

        return self._generate_mock_bars(symbol=symbol, timeframe=timeframe, limit=limit)

    def _load_csv_bars(self, csv_path: Path) -> list[Bar]:
        if not csv_path.exists():
            raise ValueError(f"CSV file not found: {csv_path}")

        required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
        with csv_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                raise ValueError("CSV is empty or missing header")
            missing = required_columns - set(reader.fieldnames)
            if missing:
                raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

            bars: list[Bar] = []
            seen_timestamps: set[datetime] = set()
            previous_timestamp: datetime | None = None
            for row_number, row in enumerate(reader, start=2):
                timestamp = _parse_timestamp(row.get("timestamp"), row_number)
                if timestamp in seen_timestamps:
                    raise ValueError(f"duplicate timestamp at row {row_number}: {timestamp.isoformat()}")
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    raise ValueError("CSV timestamps must be sorted in ascending order")
                seen_timestamps.add(timestamp)
                previous_timestamp = timestamp

                open_ = _parse_float(row.get("open"), "open", row_number)
                high = _parse_float(row.get("high"), "high", row_number)
                low = _parse_float(row.get("low"), "low", row_number)
                close = _parse_float(row.get("close"), "close", row_number)
                volume = _parse_float(row.get("volume"), "volume", row_number)

                if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
                    raise ValueError(f"prices must be > 0 at row {row_number}")
                if volume < 0:
                    raise ValueError(f"volume must be >= 0 at row {row_number}")
                if high < max(open_, close, low):
                    raise ValueError(f"invalid OHLC at row {row_number}: high is too low")
                if low > min(open_, close, high):
                    raise ValueError(f"invalid OHLC at row {row_number}: low is too high")

                bars.append(Bar(timestamp, open_, high, low, close, volume))

        if len(bars) < 100:
            raise ValueError("CSV must contain at least 100 candles for backtest")
        return bars

    def _generate_mock_bars(self, symbol: str, timeframe: str, limit: int) -> list[Bar]:
        step = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }[timeframe]

        seed = sum(ord(ch) for ch in symbol) % 37
        base = 100.0 + seed
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        bars: list[Bar] = []

        for idx in range(limit):
            timestamp = end - step * (limit - idx - 1)
            drift = idx * 0.03
            wave = sin((idx + seed) / 4.0) * 1.25
            close = base + drift + wave
            open_ = close - sin((idx + seed) / 3.0) * 0.35
            high = max(open_, close) + 0.45
            low = min(open_, close) - 0.45
            volume = 10_000 + (idx * 137 + seed * 17) % 3_000
            bars.append(Bar(timestamp, open_, high, low, close, float(volume)))

        return bars


def _parse_timestamp(value: str | None, row_number: int) -> datetime:
    if value is None or value.strip() == "":
        raise ValueError(f"timestamp is required at row {row_number}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp at row {row_number}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_float(value: str | None, column: str, row_number: int) -> float:
    if value is None or value.strip() == "":
        raise ValueError(f"{column} is required at row {row_number}")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid numeric value for {column} at row {row_number}") from exc
    if not isfinite(parsed):
        raise ValueError(f"NaN or infinite value for {column} at row {row_number}")
    return parsed
