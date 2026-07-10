# FINAL STATUS

## Project State

- Project type: rule-based crypto spot paper trading bot.
- Trading decisions: rule-based strategies only; no AI/LLM trading decisions.
- Execution modes used: backtest, compare, robustness, select_candidate.
- Live trading: not implemented.
- Real orders: not implemented.
- Real API keys: not used.
- Futures/leverage/margin: not implemented.
- Order execution path: proposals must pass `OrderGateway` and `RiskManager`.
- Market regime layer: ADX, ATR, EMA slope.
- Volume confirmation layer: current volume must be at least SMA20 volume.
- Regime rules: EMA/MACD only in `TREND`; RSI/Bollinger only in `RANGE`; `HIGH_VOLATILITY` returns `HOLD`.
- Trend pullback strategy: long-only crypto spot strategy using EMA50/EMA200, RSI, volume SMA20 and `TREND` regime.

## Data

Existing CSV datasets in `data/markets`:

- `BTCUSDT_1h.csv`
- `BTCUSDT_4h.csv`
- `ETHUSDT_1h.csv`
- `ETHUSDT_4h.csv`
- `SOLUSDT_1h.csv`
- `SOLUSDT_4h.csv`

The data directory was not empty, so the historical downloader was not run during this pass.

## Strategies Checked

- `ema_crossover`
- `rsi_mean_reversion`
- `macd_strategy`
- `bollinger_bands`
- `breakout`
- `trend_pullback`
- `buy_and_hold`

New rule-based crypto spot strategies added in this pass:

- `macd_strategy`
- `bollinger_bands`
- `breakout`
- `trend_pullback`

`rsi_mean_reversion` already existed and was included in the research run.

## Compare / Backtest Summary

Command:

```bash
.venv/bin/python main.py --mode compare --data-dir data/markets
```

Summary by strategy:

| Strategy | Avg net PnL % | Valid datasets | Robust | Rejection reasons |
| --- | ---: | ---: | --- | --- |
| `ema_crossover` | 0.4982 | 0/6 | false | too few trades |
| `breakout` | 0.3245 | 0/6 | false | net pnl not positive; too few trades |
| `bollinger_bands` | 0.2423 | 0/6 | false | too few trades |
| `rsi_mean_reversion` | -0.2927 | 0/6 | false | too few trades |
| `macd_strategy` | -0.2979 | 0/6 | false | net pnl not positive; too few trades; walk-forward unstable |
| `buy_and_hold` | -0.4009 | 0/6 | false | too few trades |

Additional diagnostic command:

```bash
.venv/bin/python main.py --mode compare --data-dir data/markets --limit 1000
```

Result: larger history increased trade counts for some strategies, but no strategy became valid robust. Failures were due to net PnL not positive, too few trades on some datasets, or walk-forward instability.

## Robustness Results

Commands run:

```bash
.venv/bin/python main.py --mode robustness --strategy ema_crossover --data-dir data/markets
.venv/bin/python main.py --mode robustness --strategy rsi_mean_reversion --data-dir data/markets
.venv/bin/python main.py --mode robustness --strategy macd_strategy --data-dir data/markets
.venv/bin/python main.py --mode robustness --strategy bollinger_bands --data-dir data/markets
.venv/bin/python main.py --mode robustness --strategy breakout --data-dir data/markets
.venv/bin/python main.py --mode robustness --strategy buy_and_hold --data-dir data/markets
```

All strategies returned:

- `datasets_tested`: 6
- `valid_datasets_count`: 0
- `robust`: false

No validation rule was weakened. The rules remain:

- minimum trades >= 20
- max drawdown <= 20%
- net PnL percent > 0
- walk-forward stable required
- robustness across datasets required

## Candidate Selection

Command:

```bash
.venv/bin/python main.py --mode select_candidate --data-dir data/markets --save-selected-config
```

Result:

```json
{
  "selected_strategy": null,
  "selected_params": null,
  "reason": "no valid robust strategy",
  "next_recommended_mode": "report_only"
}
```

Frozen config:

- File: `config/selected_candidate.json`
- `strategy`: null
- `allowed_next_mode`: `report_only`

No strategy was selected because none passed the existing validation and robustness rules.

## Paper Replay

`paper_replay` was not run.

Reason: `config/selected_candidate.json` has `allowed_next_mode: "report_only"` and `strategy: null`. Running replay with this config is intentionally forbidden by the safety rules.

## Pytest

Final command:

```bash
.venv/bin/python -m pytest
```

Latest final result:

```text
131 passed
```
