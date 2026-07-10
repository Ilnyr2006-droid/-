# Freqtrade Risk Gaps

Dry-run promotion is blocked. Freqtrade's standard configuration is not treated as a replacement for the existing RiskManager.

- Fixed stake and stoploss callbacks do not prove the 1% per-trade risk rule for every execution.
- Daily cumulative-loss behavior is not proven equivalent.
- Consecutive-loss and portfolio drawdown protections need verified callback-level behavior.
- Breakout's ATR stop mapping is not yet verified.
- The Freqtrade paper config's fixed stake amount and pricing settings were required for backtesting compatibility; they do not establish RiskManager-equivalent sizing or execution approval.
- Data equivalence and dual-engine benchmark comparison are incomplete, so no Freqtrade strategy is eligible for candidate promotion or dry-run.
