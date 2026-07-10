# Security Policy

This project is crypto spot research and paper trading only. Live trading, exchange credentials, leverage, margin, futures, shorts, FreqAI and AI/LLM trade decisions are prohibited.

The optional Freqtrade integration is Docker-contained and guarded by `freqtrade_adapter.safety_guard`. Its config must use `dry_run=true`, spot mode, empty exchange credentials and a static local pairlist. `ccxt` is permitted only inside the Freqtrade Docker image; project code must not import it. Strategy files must not import network clients such as `requests` or `httpx`.

No Freqtrade dry-run may start without a validated frozen candidate, verified hashes and closed risk adapter gaps.
