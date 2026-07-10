# Adaptive Trend Following Results

Date: 2026-07-10

## Implementation

`adaptive_trend_following` is a rule-based, long-only crypto spot strategy. It creates a BUY proposal only when the current close is above EMA200, EMA50 is above EMA200, ADX is above 20, and the existing TREND and SMA20 volume gates allow trading. It creates a SELL proposal for an existing paper position when close is below EMA50 or below the ATR trailing stop. The entry quantity is bounded below both the 1% risk limit and the 10% position-notional limit.

The strategy has no broker, network, API-key, AI, LLM, live-trading, futures, leverage, margin, or short-selling code. It returns proposals only; `OrderGateway` and `RiskManager` remain the exclusive execution and approval path.

## Verification

- `pytest`: 139 passed.
- `compare --validation-mode research --data-dir data/markets`: completed for all 8 registered strategies and 6 CSV datasets.
- `walk_forward --validation-mode research --data-dir data/markets`: completed for all six datasets. The data-directory form now reads each CSV instead of silently using mock data.
- `walk_forward --validation-mode research --strategy adaptive_trend_following --data-dir data/markets`: completed for the new strategy.
- `select_candidate --validation-mode research --data-dir data/markets --save-selected-config`: completed.

## Adaptive Strategy Robustness

| Dataset | Net PnL % | Trades | Max drawdown | Walk-forward stable | Validation result |
| --- | ---: | ---: | ---: | --- | --- |
| BTCUSDT_1h | -0.2509 | 15 | 0.61% | false | net pnl not positive |
| BTCUSDT_4h | 0.0000 | 0 | 0.00% | true | too few trades |
| ETHUSDT_1h | 0.0554 | 11 | 0.60% | false | walk-forward unstable |
| ETHUSDT_4h | 0.0000 | 0 | 0.00% | true | too few trades |
| SOLUSDT_1h | -1.1469 | 22 | 1.36% | true | net pnl not positive |
| SOLUSDT_4h | -0.5553 | 3 | 0.66% | true | too few trades |

Aggregate result: average net PnL is `-0.3163%`, worst drawdown is `1.36%`, valid datasets are `0/6`, and `robust` is `false`.

The direct walk-forward run for this strategy was unstable on BTCUSDT 1h and ETHUSDT 1h; it was stable on the other four datasets. The research configuration uses a 240-bar train window and 120-bar test window, yielding one segment per CLI dataset window. This is enough to reject the strategy under the current rules, but not enough evidence to promote it.

## Candidate Selection

No strategy qualified as valid and robust. `config/selected_candidate.json` therefore contains `strategy: null` and permits only `report_only`; `paper_replay` is not authorized.

The candidate-selection result is correct under the existing validation rules: minimum trade counts, positive net PnL, walk-forward stability, robustness, and all risk limits were left unchanged.
