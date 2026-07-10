# Freqtrade Migration Plan

## Scope

Freqtrade is an optional Docker-contained engine for historical data download, backtesting, fees, lifecycle tooling and later dry-run monitoring. The existing Python engine, RiskManager, OrderGateway, research analytics and paper replay remain authoritative and are not removed.

## Ownership

- Freqtrade: independent OHLCV data, strategy lifecycle, backtesting, lookahead and recursive analysis.
- This project: validation thresholds, chronological splits, holdout isolation, robustness, candidate selection, artifact integrity and security gates.
- Adapter: config validation, command allowlist, data conversion, metric comparison and promotion blocking.

## Metric Differences

Expected differences include next-candle versus candle-close execution, intrabar stop handling, stake sizing, fee rounding, precision, warmup and open-position treatment. Dual-engine benchmark records and explains material differences instead of silently averaging them away.

## Rollback

Delete or stop the optional Docker service and ignore `freqtrade_user_data/`. The legacy engine remains unchanged and continues to own all paper execution. No migration step can enable live trading.
