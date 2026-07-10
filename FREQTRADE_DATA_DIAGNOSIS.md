# Freqtrade Data Diagnosis

Artifact: `results/freqtrade_data_diagnosis_20260710T120420078577Z.json`.

The comparison uses only exact common UTC candle-open timestamps. It never replaces source data, applies timestamp offsets, or treats different historical coverage as a price mismatch.

## Findings

- All 16 datasets are Binance spot OHLCV and use UTC candle-open timestamps.
- No one-bar timestamp shift was detected.
- All eight `4h` datasets are `COVERAGE_DIFFERS_ONLY`: OHLCV matches on the common range, while Freqtrade has longer history and recorded exchange gaps. They require a fixed common timerange for later comparison.
- All eight `1h` datasets have one OHLC mismatch on the common range. It is the final common candle, classified as `FINAL_CANDLE_MAY_BE_OPEN`, not a systematic source-price difference.
- Volume differs for the `1h` datasets, so volume-dependent strategies remain blocked even after excluding the final candle.

## Dual Benchmark Readiness

No dataset is cleared for automatic dual-engine comparison. `4h` datasets need a documented common timerange and gap policy. `1h` datasets need a documented closed-candle cutoff and a volume compatibility decision. No data has been redownloaded or modified.
