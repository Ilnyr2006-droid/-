from __future__ import annotations

from enum import StrEnum

from models import AccountState, Bar


class MarketRegime(StrEnum):
    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


def detect_market_regime(
    bars: list[Bar],
    adx_period: int = 14,
    atr_period: int = 14,
    ema_period: int = 20,
    high_volatility_atr_pct: float = 0.035,
    trend_adx_threshold: float = 20.0,
    trend_slope_threshold: float = 0.0005,
) -> MarketRegime:
    required = max(adx_period * 2 + 1, atr_period + 1, ema_period + 2)
    if len(bars) < required:
        return MarketRegime.RANGE

    closes = [bar.close for bar in bars]
    atr = _atr(bars, atr_period)
    atr_pct = atr / closes[-1] if closes[-1] else 0.0
    if atr_pct >= high_volatility_atr_pct:
        return MarketRegime.HIGH_VOLATILITY

    adx = _adx(bars, adx_period)
    ema_values = _ema_series(closes, ema_period)
    ema_slope = (ema_values[-1] - ema_values[-2]) / ema_values[-2] if ema_values[-2] else 0.0
    if adx >= trend_adx_threshold and abs(ema_slope) >= trend_slope_threshold:
        return MarketRegime.TREND

    return MarketRegime.RANGE


def volume_confirmed(bars: list[Bar], period: int = 20, multiplier: float = 1.0) -> bool:
    if len(bars) < period:
        return True
    volume_sma = sum(bar.volume for bar in bars[-period:]) / period
    return bars[-1].volume >= volume_sma * multiplier


def account_market_regime(account_state: AccountState, bars: list[Bar]) -> MarketRegime:
    if account_state.market_regime is not None:
        try:
            return MarketRegime(account_state.market_regime)
        except ValueError:
            return detect_market_regime(bars)
    return detect_market_regime(bars)


def trade_allowed_by_regime_and_volume(
    bars: list[Bar],
    account_state: AccountState,
    allowed_regimes: set[MarketRegime],
    volume_period: int = 20,
) -> bool:
    regime = account_market_regime(account_state, bars)
    if regime == MarketRegime.HIGH_VOLATILITY:
        if not account_state.allow_high_volatility_research_mode:
            return False
        return volume_confirmed(
            bars,
            volume_period,
            multiplier=account_state.volume_filter_multiplier,
        )
    if regime not in allowed_regimes:
        return False
    return volume_confirmed(
        bars,
        volume_period,
        multiplier=account_state.volume_filter_multiplier,
    )


def _true_ranges(bars: list[Bar]) -> list[float]:
    ranges: list[float] = []
    for idx, bar in enumerate(bars):
        if idx == 0:
            ranges.append(bar.high - bar.low)
            continue
        previous_close = bars[idx - 1].close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return ranges


def _atr(bars: list[Bar], period: int) -> float:
    ranges = _true_ranges(bars)
    window = ranges[-period:]
    return sum(window) / len(window)


def calculate_atr(bars: list[Bar], period: int = 14) -> float:
    """Return ATR from the supplied historical bars only."""
    if period <= 0:
        raise ValueError("ATR period must be positive")
    if len(bars) < 2:
        return 0.0
    return _atr(bars, period)


def _adx(bars: list[Bar], period: int) -> float:
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges = _true_ranges(bars)
    for idx in range(1, len(bars)):
        up_move = bars[idx].high - bars[idx - 1].high
        down_move = bars[idx - 1].low - bars[idx].low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    dx_values: list[float] = []
    for end in range(period, len(plus_dm) + 1):
        tr_sum = sum(true_ranges[end - period + 1 : end + 1])
        if tr_sum == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * sum(plus_dm[end - period : end]) / tr_sum
        minus_di = 100.0 * sum(minus_dm[end - period : end]) / tr_sum
        denominator = plus_di + minus_di
        dx_values.append(0.0 if denominator == 0 else 100.0 * abs(plus_di - minus_di) / denominator)

    if not dx_values:
        return 0.0
    window = dx_values[-period:]
    return sum(window) / len(window)


def calculate_adx(bars: list[Bar], period: int = 14) -> float:
    """Return ADX from the supplied historical bars only."""
    if period <= 0:
        raise ValueError("ADX period must be positive")
    if len(bars) < 2:
        return 0.0
    return _adx(bars, period)


def _ema_series(values: list[float], period: int) -> list[float]:
    multiplier = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
        result.append(ema)
    return result
