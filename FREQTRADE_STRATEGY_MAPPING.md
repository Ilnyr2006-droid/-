# Freqtrade Strategy Mapping

## EMA Crossover

- Legacy: EMA 12/26 crossover, trend/volume filter, 1% stop, crossover exit.
- Adapter: pandas EMA 12/26 with shifted crossover, ADX/EMA20/ATR/volume filters and `can_short = false`.
- Known difference: ADX proxy and Freqtrade candle execution must be compared in dual-engine benchmark.
- Verification: Freqtrade `2026.5.1` loaded the strategy with `can_short = false` and `startup_candle_count = 30`; fixed-matrix backtests, lookahead analysis, and recursive analysis completed. Equivalence remains unproven.

## RSI Mean Reversion

- Legacy: six-change simple RSI below 45 in RANGE, exit above 55, 2% stop.
- Adapter: rolling-sum simple RSI retains the same 6-change formula, volume and ADX range filter.
- Known difference: Freqtrade trade lifecycle may exit at a different candle according to its execution model.
- Verification: Freqtrade `2026.5.1` loaded the strategy with `can_short = false`; fixed-matrix backtests, lookahead analysis, and recursive analysis completed. Equivalence remains unproven.

## Breakout

- Legacy: previous five-bar high entry, previous three-bar low exit, volume confirmation and ATR-based stop proposal.
- Adapter: shifted rolling high/low and simple ATR proxy, long-only.
- Known difference: dynamic ATR stop cannot be claimed equivalent until a verified Freqtrade callback is implemented; this blocks dry-run promotion.
- Verification: Freqtrade `2026.5.1` loaded the strategy with `can_short = false`; fixed-matrix backtests, lookahead analysis, and recursive analysis completed. The ATR-stop gap remains blocking.
