from __future__ import annotations

from statistics import mean, pstdev

from models import Bar


def calculate_volume_features(bars: list[Bar]) -> dict[str, float | None]:
    """Return current volume relative to its historical 20-bar distribution."""
    if len(bars) < 20:
        return {"volume_sma_ratio": None, "volume_zscore": None}
    volumes = [bar.volume for bar in bars[-20:]]
    average = mean(volumes)
    deviation = pstdev(volumes)
    current = volumes[-1]
    return {
        "volume_sma_ratio": current / average if average else None,
        "volume_zscore": (current - average) / deviation if deviation else 0.0,
    }
