from __future__ import annotations

from models import Bar


def calculate_momentum_features(bars: list[Bar]) -> dict[str, float | None]:
    """Return percentage momentum features without looking beyond the last bar."""
    closes = [bar.close for bar in bars]
    return {
        "roc": _return_percent(closes, 14),
        "returns_7": _return_percent(closes, 7),
        "returns_30": _return_percent(closes, 30),
    }


def _return_percent(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback or closes[-lookback - 1] == 0:
        return None
    return (closes[-1] / closes[-lookback - 1] - 1.0) * 100


def calculate_rsi(bars: list[Bar], period: int = 14) -> float | None:
    """Return RSI from the supplied history, or None when its window is incomplete."""
    if period <= 0:
        raise ValueError("RSI period must be positive")
    if len(bars) < period + 1:
        return None
    closes = [bar.close for bar in bars[-period - 1 :]]
    gains = 0.0
    losses = 0.0
    for previous, current in zip(closes, closes[1:]):
        change = current - previous
        if change >= 0:
            gains += change
        else:
            losses += abs(change)
    if losses == 0:
        return 100.0
    relative_strength = gains / losses
    return 100.0 - (100.0 / (1.0 + relative_strength))
