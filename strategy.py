from __future__ import annotations

from models import Bar, Signal


class EMACrossoverStrategy:
    def __init__(self, fast_period: int = 12, slow_period: int = 26) -> None:
        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("EMA periods must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def signal(self, bars: list[Bar]) -> Signal:
        min_bars = self.slow_period + 2
        if len(bars) < min_bars:
            return Signal.HOLD

        closes = [bar.close for bar in bars]
        fast = _ema_series(closes, self.fast_period)
        slow = _ema_series(closes, self.slow_period)

        previous_fast, current_fast = fast[-2], fast[-1]
        previous_slow, current_slow = slow[-2], slow[-1]

        if previous_fast <= previous_slow and current_fast > current_slow:
            return Signal.BUY
        if previous_fast >= previous_slow and current_fast < current_slow:
            return Signal.SELL
        return Signal.HOLD


def generate_signal(bars: list[Bar], fast_period: int = 12, slow_period: int = 26) -> Signal:
    return EMACrossoverStrategy(fast_period, slow_period).signal(bars)


def _ema_series(values: list[float], period: int) -> list[float]:
    multiplier = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
        result.append(ema)
    return result
