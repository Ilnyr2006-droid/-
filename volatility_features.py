from __future__ import annotations

from statistics import mean, pstdev

from market_regime import calculate_atr
from models import Bar


def calculate_volatility_features(bars: list[Bar]) -> dict[str, float | None]:
    """Return ATR, rolling-return volatility, and current candle range in percent."""
    if not bars:
        return {"atr_percent": None, "rolling_volatility": None, "candle_range_percent": None}

    closes = [bar.close for bar in bars]
    price = closes[-1]
    returns = [
        (current / previous - 1.0) * 100
        for previous, current in zip(closes, closes[1:])
        if previous != 0
    ]
    return {
        "atr_percent": calculate_atr(bars, 14) / price * 100 if len(bars) >= 15 and price else None,
        "rolling_volatility": pstdev(returns[-20:]) if len(returns) >= 20 else None,
        "candle_range_percent": (bars[-1].high - bars[-1].low) / price * 100 if price else None,
    }


def average_atr_percent(
    bars: list[Bar],
    atr_period: int = 14,
    lookback: int = 20,
) -> float | None:
    """Return the mean ATR percent of completed prior bars, excluding the current bar."""
    first_end = atr_period + 1
    if len(bars) <= first_end:
        return None
    values: list[float] = []
    for end in range(first_end, len(bars)):
        window = bars[:end]
        price = window[-1].close
        if price:
            values.append(calculate_atr(window, atr_period) / price * 100)
    prior_values = values[-lookback:]
    return mean(prior_values) if prior_values else None
