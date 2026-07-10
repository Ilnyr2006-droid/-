# Freqtrade Migration Status

- Current phase: Phase 1–2 Docker verification and backtesting completed; equivalence work remains open.
- Docker availability: verified on 2026-07-10. Docker `29.6.1`, Compose `v5.2.0`, context `desktop-linux`, Linux `arm64` container runtime.
- Pinned image: `freqtradeorg/freqtrade:2026.5.1`.
  Digest: `freqtradeorg/freqtrade@sha256:d47d7053dc07eca2ace20385575143090ba88621007e5e8b76052dca6038799a`.
  Image ID: `sha256:c43cc4decec78271b70bfdf963af3944a4314b9e7fc308469ea5437dde766ecf`.
  Verified Freqtrade version: `2026.5.1`.
- Safety config: FreqAI, Telegram, API server, webhook, margin, leverage, futures, and short selling remain disabled or absent. The wrapper records a config SHA-256 for every command and allows only research commands.
- Dataset status: 16 independent Binance spot OHLCV pair/timeframe datasets were downloaded under `freqtrade_user_data/data/binance/`; `data/markets/` was not modified. The datasets cover BTC, ETH, SOL, BNB, XRP, ADA, LINK, and AVAX against USDT at `1h` and `4h`.
- Strategy loading: `EmaCrossoverStrategy`, `RsiMeanReversionStrategy`, and `BreakoutStrategy` were discovered with Freqtrade status `OK`.
- Backtests: all 18 fixed combinations of the three strategies, BTC/ETH/SOL, and `1h`/`4h` completed successfully. Wrapper artifacts and raw Freqtrade results are retained under `results/` and `freqtrade_user_data/backtest_results/`.
- Lookahead and recursive analyses: completed successfully for all three strategies on BTC/USDT `1h`, timerange `20220101-20240101`; artifacts are retained in `results/`.
- Data comparison: completed with native Feather support. Artifact: `results/freqtrade_data_comparison_20260710T115714399377Z.json`; 16 datasets compared, 2 compatible and 14 critical mismatches. These mismatches block equivalence promotion.
- Root-cause diagnosis: `results/freqtrade_data_diagnosis_20260710T120420078577Z.json` found eight `4h` coverage-only differences and eight `1h` final-candle OHLC differences. No timestamp shift was detected. The final candle and volume mismatch remain blockers for comparison of volume-dependent strategies.
- Dual-engine comparison: blocked. `main.py --mode freqtrade_dual_benchmark` is not registered, so no equivalence result was fabricated.
- Dual-engine readiness: `results/freqtrade_dual_eligibility_20260710T121047377760Z.json` contains 48 combinations; 6 are data-eligible and 42 are blocked by final-candle, volume, or gap-policy constraints. The CLI reads artifacts only and did not execute either engine.
- Risk gaps: open; see `FREQTRADE_RISK_GAPS.md`.
- Candidate status: none.
- Dry-run status: blocked. No `trade`, dry-run loop, live order, or real API key was used.
- Readiness: `NOT_READY`.

## Rollback

Do not start the compose service. The legacy engine remains fully independent; remove the optional `freqtrade_*` directories to abandon this migration scaffolding.
