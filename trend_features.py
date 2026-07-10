from __future__ import annotations

from market_regime import calculate_adx
from models import Bar


def calculate_trend_features(bars: list[Bar]) -> dict[str, float | None]:
    """Trend features based exclusively on the supplied historical window."""
    closes = [bar.close for bar in bars]
    ema_fast = _ema_series(closes, 50)
    ema_slow = _ema_series(closes, 200)
    ema_distance = None
    if len(closes) >= 200 and ema_slow[-1] != 0:
        ema_distance = (ema_fast[-1] - ema_slow[-1]) / ema_slow[-1] * 100

    ema_slope = None
    if len(closes) >= 51 and ema_fast[-2] != 0:
        ema_slope = (ema_fast[-1] - ema_fast[-2]) / ema_fast[-2] * 100

    return {
        "ema_distance": ema_distance,
        "ema_slope": ema_slope,
        "adx": calculate_adx(bars, 14) if len(bars) >= 29 else None,
    }


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
        result.append(ema)
    return result
