# VALIDATION COMPARISON

Scope: research validation pipeline comparison only. BrokerPaper, RiskManager, crypto spot rules, live-safety, leverage/margin/futures restrictions and order execution safety were not changed.

## Research Config

Config file: `research_config.yaml`

- `walk_forward_train_size`: 240
- `walk_forward_test_size`: 120
- `min_trades_by_timeframe`: 1h=10, 4h=5, intraday lower-timeframes stricter
- `volume_filter_multiplier`: 0.8
- `allow_high_volatility_research_mode`: true

Modes:

- `paper`: current strict filters and validation behavior.
- `research`: analysis-only mode with softer volume confirmation, optional high-volatility research allowance, timeframe-aware minimum trades and larger walk-forward windows.

## Compare Summary

| Strategy | Paper trades | Paper avg net PnL % | Paper worst DD | Paper robust | Research trades | Research avg net PnL % | Research worst DD | Research robust | Research stable datasets |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | ---: |
| `breakout` | 30 | 0.4915 | 0.0149 | false | 42 | 0.3584 | 0.0152 | false | 3/6 |
| `ema_crossover` | 3 | 0.3846 | 0.0091 | false | 4 | 0.2098 | 0.0057 | false | 4/6 |
| `rsi_mean_reversion` | 32 | 0.1496 | 0.0345 | false | 42 | -0.2735 | 0.0355 | false | 3/6 |
| `macd_strategy` | 31 | 0.0658 | 0.0172 | false | 48 | 0.1887 | 0.0204 | false | 3/6 |
| `trend_pullback` | 4 | -0.0211 | 0.0018 | false | 10 | -0.0688 | 0.0050 | false | 5/6 |
| `bollinger_bands` | 19 | -0.1695 | 0.0228 | false | 28 | -0.0155 | 0.0241 | false | 4/6 |
| `buy_and_hold` | 6 | -0.4009 | 0.0301 | false | 6 | -0.6528 | 0.0382 | false | 4/6 |

## Candidate Selection

| Mode | Selected strategy | Next recommended mode | Warnings |
| --- | --- | --- | --- |
| paper | `None` | `report_only` | no robust strategies |
| research | `None` | `report_only` | no robust strategies |

No valid robust candidate was selected in either mode. This is expected: research mode improves diagnostic coverage but does not force a strategy to become tradable.

## Walk-Forward Check

Command basis: `ema_crossover` on `BTCUSDT_1h.csv`.

| Mode | Train size | Test size | Stable | Segments | First train period | First test period | PnL train | PnL test | Max DD test |
| --- | ---: | ---: | --- | ---: | --- | --- | ---: | ---: | ---: |
| paper | 120 | 60 | true | 1 | 2026-07-02 -> 2026-07-07 | 2026-07-07 -> 2026-07-09 | 0.00 | 0.00 | 0.0000 |
| research | 240 | 120 | false | 1 | 2026-06-24 -> 2026-07-04 | 2026-07-04 -> 2026-07-09 | 481.07 | 0.00 | 0.0000 |

## Interpretation

- Research mode is intentionally softer for analysis, not for live/paper execution.
- Research mode changes signal admission only through `AccountState` analysis flags; default paper mode remains strict.
- Timeframe-aware minimum trades prevent 4h/1d strategies from being judged by the same trade-count threshold as 1h/lower timeframes.
- Larger walk-forward windows make stability estimates less dependent on short 60-candle test slices.
- The current datasets still produce zero robust candidates in both modes; this indicates the strategies remain weak or sparse, not that validation should be bypassed.

## Commands Run

```bash
.venv/bin/python -m pytest
.venv/bin/python main.py --mode compare --data-dir data/markets --validation-mode paper
.venv/bin/python main.py --mode compare --data-dir data/markets --validation-mode research
.venv/bin/python main.py --mode walk_forward --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/markets/BTCUSDT_1h.csv --validation-mode paper
.venv/bin/python main.py --mode walk_forward --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/markets/BTCUSDT_1h.csv --validation-mode research
.venv/bin/python main.py --mode select_candidate --data-dir data/markets --validation-mode paper
.venv/bin/python main.py --mode select_candidate --data-dir data/markets --validation-mode research
```
