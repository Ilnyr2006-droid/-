# WALK-FORWARD ANALYSIS

Scope: analysis only. Trading rules, RiskManager, validation rules, live-trading safeguards, and strategy code were not changed for this report.

Command basis: `run_walk_forward(..., train_size=120, test_size=60, limit=300)` across all CSV files in `data/markets`.

## Executive Summary

| Strategy | Stable datasets | Stable segments | Positive test segments | Low-trade segments | Avg train trades | Avg test trades | Main diagnosis |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ema_crossover` | 0/6 | 14/18 | 0/18 | 18/18 | 0.28 | 0.00 | too few trades / filters too strict |
| `rsi_mean_reversion` | 1/6 | 12/18 | 6/18 | 18/18 | 2.72 | 1.78 | too few trades / filters too strict |
| `macd_strategy` | 0/6 | 13/18 | 3/18 | 18/18 | 2.06 | 0.89 | too few trades / filters too strict |
| `bollinger_bands` | 1/6 | 14/18 | 4/18 | 18/18 | 1.61 | 0.72 | too few trades / filters too strict |
| `breakout` | 0/6 | 11/18 | 8/18 | 18/18 | 2.94 | 2.11 | too few trades / filters too strict |
| `trend_pullback` | 0/6 | 18/18 | 0/18 | 18/18 | 0.00 | 0.00 | too few trades / filters too strict |
| `buy_and_hold` | 4/6 | 15/18 | 12/18 | 18/18 | 1.00 | 1.00 | too few trades / filters too strict |

## Root Cause Assessment

1. Overfitting: not the primary explanation. The project is not selecting tuned parameters from train windows in walk-forward. Some strategies show train-positive/test-negative behavior, but this is dominated by sparse trading and regime/data sensitivity rather than parameter fitting.
2. Too few trades: yes, this is the dominant failure. Every strategy has low-trade segments, and most test windows have fewer than 20 trades. Several strategies have many zero-trade test windows.
3. Too strict filters: yes. Regime + volume confirmation, long-only spot rules, stop-loss requirements, and strategy-specific entry gates sharply reduce signal frequency. `trend_pullback` and `ema_crossover` are the clearest examples.
4. Data problem: partial. The CSV files are structurally valid, but the 120/60 walk-forward windows can be too short for slow/trend strategies and mixed 1h/4h datasets create different opportunity density. This is a sampling/window-size issue, not an OHLCV validation problem.

## `ema_crossover`

- Stable datasets: 0/6.
- Stable segments: 14/18.
- Positive test segments: 0/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 18/18.
- Train-positive/test-nonpositive segments: 4/18.
- Nonpositive test PnL segments: 18/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: the strategy is mainly under-trading. TREND/regime requirements plus slow moving-average structure leave too few trades in 60-candle test windows. This is not strong evidence of overfitting; it is primarily sparse signal generation and strict filtering.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 131.18 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 545.65 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 298.75 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 1060.16 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -50.18 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |

## `rsi_mean_reversion`

- Stable datasets: 1/6.
- Stable segments: 12/18.
- Positive test segments: 6/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 3/18.
- Train-positive/test-nonpositive segments: 6/18.
- Nonpositive test PnL segments: 12/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: RANGE-only logic does not produce enough validated trades in most windows. Some train/test degradation appears, but the dominant issue is too few trades after regime and volume confirmation.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 162.89 | -10.58 | 0.04% | 5 | 2 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 605.25 | -70.64 | 0.34% | 1 | 5 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -26.18 | -194.29 | 0.30% | 5 | 2 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -1339.36 | 0.00 | 0.00% | 5 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1275.65 | -388.52 | 0.57% | 2 | 2 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 752.28 | 0.39% | 0 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 423.41 | 0.00 | 0.00% | 3 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 1313.61 | 64.43 | 0.30% | 1 | 3 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -27.80 | -160.92 | 0.32% | 3 | 2 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -282.76 | 259.69 | 0.97% | 7 | 1 | too few trades in train/test segment |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1752.29 | -315.32 | 0.80% | 2 | 2 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -344.61 | 1117.34 | 0.48% | 2 | 1 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 1175.28 | 105.49 | 0.23% | 3 | 3 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 1038.84 | -18.37 | 0.26% | 1 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 20.14 | -314.34 | 0.52% | 3 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -2227.68 | 0.00 | 0.00% | 3 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -2107.09 | 319.06 | 0.92% | 2 | 1 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 425.64 | -319.40 | 0.49% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |

## `macd_strategy`

- Stable datasets: 0/6.
- Stable segments: 13/18.
- Positive test segments: 3/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 8/18.
- Train-positive/test-nonpositive segments: 5/18.
- Nonpositive test PnL segments: 15/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: this strategy trades more often than EMA-style strategies, but still has low-trade test windows and several train-positive/test-nonpositive segments. This indicates regime sensitivity and weak out-of-sample persistence, not just sparse signals.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 456.86 | 74.14 | 0.06% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | -32.29 | -169.15 | 0.20% | 3 | 1 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 67.48 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -901.39 | 0.00 | 0.00% | 5 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 452.00 | -219.30 | 0.50% | 1 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -219.30 | -253.25 | 0.50% | 3 | 3 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | -105.51 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | -170.93 | -170.98 | 0.24% | 4 | 1 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -170.98 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -958.59 | 0.00 | 0.00% | 3 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 208.48 | 413.99 | 0.26% | 1 | 1 | too few trades in train/test segment |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 413.99 | -247.88 | 0.39% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 1085.51 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | -137.86 | 0.18% | 0 | 1 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -137.86 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -1096.18 | 21.69 | 0.02% | 3 | 2 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 21.69 | -251.69 | 0.49% | 2 | 2 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -230.06 | 0.00 | 0.00% | 4 | 0 | too few trades in train/test segment; test pnl not positive |

## `bollinger_bands`

- Stable datasets: 1/6.
- Stable segments: 14/18.
- Positive test segments: 4/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 9/18.
- Train-positive/test-nonpositive segments: 4/18.
- Nonpositive test PnL segments: 14/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: RANGE-only logic does not produce enough validated trades in most windows. Some train/test degradation appears, but the dominant issue is too few trades after regime and volume confirmation.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | -158.26 | 285.69 | 0.05% | 2 | 1 | too few trades in train/test segment |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | -73.85 | 25.37 | 0.22% | 2 | 3 | too few trades in train/test segment |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 278.89 | 83.74 | 0.19% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -1718.61 | -130.93 | 0.33% | 1 | 1 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1053.56 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 22.67 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | -20.64 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 1424.29 | 86.65 | 0.30% | 1 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 88.67 | -33.14 | 0.19% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -152.56 | -71.54 | 0.94% | 3 | 1 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -159.57 | 0.00 | 0.00% | 3 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -582.60 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 1179.02 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | -100.95 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | -71.27 | 0.23% | 0 | 2 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 164.64 | 0.00 | 0.00% | 2 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -872.17 | -284.88 | 0.55% | 3 | 2 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |

## `breakout`

- Stable datasets: 0/6.
- Stable segments: 11/18.
- Positive test segments: 8/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 1/18.
- Train-positive/test-nonpositive segments: 7/18.
- Nonpositive test PnL segments: 10/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: this strategy trades more often than EMA-style strategies, but still has low-trade test windows and several train-positive/test-nonpositive segments. This indicates regime sensitivity and weak out-of-sample persistence, not just sparse signals.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | -23.81 | -58.90 | 0.08% | 5 | 3 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 545.65 | -262.41 | 0.29% | 1 | 5 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -385.31 | -12.19 | 0.06% | 9 | 2 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -194.59 | 0.04 | 0.77% | 2 | 2 | too few trades in train/test segment |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 44.78 | -159.90 | 0.16% | 3 | 4 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -360.24 | 530.57 | 0.39% | 6 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | -119.74 | 477.49 | 0.11% | 7 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 937.87 | -115.00 | 0.28% | 3 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 412.72 | 0.00 | 0.00% | 1 | 0 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -80.67 | 208.48 | 0.96% | 2 | 1 | too few trades in train/test segment |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 208.48 | -131.27 | 0.13% | 1 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -122.30 | 790.57 | 0.47% | 3 | 1 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 941.00 | 128.94 | 0.23% | 3 | 1 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 607.84 | -157.87 | 0.29% | 1 | 3 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -145.39 | -23.00 | 0.02% | 3 | 2 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 620.08 | 1.05% | 0 | 1 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -642.85 | 1022.08 | 0.35% | 2 | 3 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 1442.79 | -64.06 | 0.78% | 1 | 2 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |

## `trend_pullback`

- Stable datasets: 0/6.
- Stable segments: 18/18.
- Positive test segments: 0/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 18/18.
- Train-positive/test-nonpositive segments: 0/18.
- Nonpositive test PnL segments: 18/18.
- Instability reasons observed: test pnl not positive, too few trades in train/test segment.

Assessment: the strategy is mainly under-trading. TREND/regime requirements plus slow moving-average structure leave too few trades in 60-candle test windows. This is not strong evidence of overfitting; it is primarily sparse signal generation and strict filtering.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 0.00 | 0.00 | 0.00% | 0 | 0 | too few trades in train/test segment; test pnl not positive |

## `buy_and_hold`

- Stable datasets: 4/6.
- Stable segments: 15/18.
- Positive test segments: 12/18.
- Segments with too few train/test trades: 18/18.
- Zero-trade test segments: 0/18.
- Train-positive/test-nonpositive segments: 3/18.
- Nonpositive test PnL segments: 6/18.
- Instability reasons observed: positive train pnl failed in test, test pnl not positive, too few trades in train/test segment.

Assessment: buy-and-hold is not naturally compatible with the minimum-trade validation rule. It can show stable segments, but trade count is structurally too low for the project validation policy.

| Dataset | Segment | Train period | Test period | PnL train | PnL test | Max DD test | Train trades | Test trades | Segment reason |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTCUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 119.78 | 242.57 | 0.08% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 487.33 | 1.73 | 0.32% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 235.82 | 16.87 | 0.39% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -2085.55 | 391.03 | 0.79% | 1 | 1 | too few trades in train/test segment |
| BTCUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1408.70 | -588.86 | 0.86% | 1 | 1 | too few trades in train/test segment; test pnl not positive |
| BTCUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -141.28 | 619.97 | 0.39% | 1 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 307.18 | 496.73 | 0.11% | 1 | 1 | too few trades in train/test segment |
| ETHUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 1192.06 | -29.86 | 0.29% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 431.90 | -129.53 | 0.49% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| ETHUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -2325.32 | 539.89 | 0.98% | 1 | 1 | too few trades in train/test segment |
| ETHUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1554.33 | -683.48 | 1.28% | 1 | 1 | too few trades in train/test segment; test pnl not positive |
| ETHUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | -58.37 | 1052.76 | 0.47% | 1 | 1 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 1 | 2026-06-27 -> 2026-07-02 | 2026-07-02 -> 2026-07-04 | 1051.51 | 55.80 | 0.23% | 1 | 1 | too few trades in train/test segment |
| SOLUSDT_1h.csv | 2 | 2026-06-29 -> 2026-07-04 | 2026-07-04 -> 2026-07-07 | 892.75 | -75.78 | 0.33% | 1 | 1 | too few trades in train/test segment; positive train pnl failed in test; test pnl not positive |
| SOLUSDT_1h.csv | 3 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | -27.96 | -346.15 | 0.73% | 1 | 1 | too few trades in train/test segment; test pnl not positive |
| SOLUSDT_4h.csv | 1 | 2026-05-21 -> 2026-06-09 | 2026-06-10 -> 2026-06-19 | -2512.23 | 953.24 | 1.07% | 1 | 1 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 2 | 2026-05-31 -> 2026-06-19 | 2026-06-20 -> 2026-06-29 | -1567.84 | 442.24 | 1.15% | 1 | 1 | too few trades in train/test segment |
| SOLUSDT_4h.csv | 3 | 2026-06-10 -> 2026-06-29 | 2026-06-30 -> 2026-07-09 | 1793.55 | 619.27 | 0.80% | 1 | 1 | too few trades in train/test segment |

## Conclusion

The universal `walk_forward_stable=false` outcome is caused primarily by insufficient trade density under strict rule-based filters and short walk-forward test windows. There is some train/test degradation in MACD, breakout, RSI and Bollinger, but the project currently rejects strategies mostly because the validation policy requires at least 20 trades and walk-forward stability while many test segments have zero to a few trades. The data files are valid; the issue is opportunity density and regime sensitivity across mixed 1h/4h market slices.
