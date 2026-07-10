# crypto-spot-paper-trading-bot

Python 3.11+ rule-based crypto spot paper trading bot для research/backtest/replay. Это не AI/LLM trading system: торговые решения принимают только rule-based strategies.

Проект работает только в paper/backtest/replay режимах. Реальных ордеров, live trading, futures, margin, leverage, broker/exchange подключений и реальных API keys здесь нет.

Supported symbols examples: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`.

Supported data source: CSV historical candles.

## Crypto Spot Rules

- Только crypto spot.
- Quote currency по умолчанию: `USDT`.
- Символ должен быть spot pair формата `BTCUSDT`, `ETHUSDT`, `SOLUSDT`.
- Символы с `PERP`, `FUTURES`, `SWAP` запрещены.
- Futures, leverage, margin и short-selling запрещены.
- Разрешенные решения: `BUY`, `SELL`, `HOLD`.
- `SELL` не может продавать больше, чем есть в paper position.
- Все сделки проходят через `OrderGateway` и `RiskManager`.
- `BrokerPaper.submit_order()` принимает только signed `ApprovedOrder`.

## Модули

- `data_provider.py` - OHLCV через `get_bars(symbol, timeframe, limit)`, включая CSV historical candles и deterministic mock data для тестов.
- `crypto_rules.py` - crypto spot symbol/order validation: USDT spot pairs only, no futures/perps/swaps, no leverage, no short-selling.
- `market_regime.py` - rule-based market regime + volume confirmation filter: `TREND`, `RANGE`, `HIGH_VOLATILITY` через ADX, ATR, EMA slope и volume SMA20.
- `strategy.py` - rule-based EMA crossover: `BUY`, `SELL`, `HOLD`.
- `risk_manager.py` - 1% риск на сделку, 10% max position, 3% дневной лимит убытка, обязательный stop-loss, запрет плеча.
- `order_gateway.py` - единый безопасный шлюз исполнения: проверяет риск, создает `ApprovedOrder` и только затем передает его paper-брокеру.
- `broker_paper.py` - симулятор баланса, позиций и сделок без live trading mode; принимает только `ApprovedOrder`, сырые ордера запрещены.
- `backtest.py` - PnL, winrate, max drawdown, Sharpe-like metric.
- `agent.py` - rule-based paper runner; исполнение идет только через `OrderGateway`, `RiskManager` и `BrokerPaper`; решения пишутся в `journal.jsonl`.
- `tests/` - проверки риск-менеджера, стратегии и невозможности live trading.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Download Historical Data

Отдельный инструмент `tools/download_data.py` скачивает только historical crypto spot OHLCV и сохраняет только CSV. Он не хранит API keys, не подключает live trading и не создает ордера.

```bash
python tools/download_data.py \
  --symbol BTCUSDT \
  --timeframe 1h \
  --days 365 \
  --output data/markets/BTCUSDT_1h.csv
```

CSV формат:

```text
timestamp,open,high,low,close,volume
```

После скачивания данные нормализуются: timestamps сортируются по возрастанию, duplicate timestamps удаляются, OHLCV проверяется, derivative symbols (`PERP`, `FUTURES`, `SWAP`) отклоняются.

## Запуск rule-based runner

```bash
python agent.py
```

После запуска появится или обновится `journal.jsonl`.

Paper-режим через CLI:

```bash
python main.py --mode paper --symbol BTCUSDT
```

Report-only режим анализирует сигнал и риск, но не совершает даже paper-сделку:

```bash
python main.py --mode report_only --symbol BTCUSDT
```

В `journal.jsonl` будет записан отчет с полями `symbol`, `signal`, `entry`, `stop_loss`, `take_profit`, `risk_percent`, `reason`.

Backtest через главный CLI:

```bash
python main.py --mode backtest --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
python main.py --mode backtest --symbol ETHUSDT --strategy rsi_mean_reversion --data-source csv --csv-path data/ETHUSDT_1h.csv
python main.py --mode backtest --symbol SOLUSDT --strategy buy_and_hold --data-source csv --csv-path data/SOLUSDT_1h.csv
python main.py --mode backtest --symbol BTCUSDT --strategy adaptive_trend_following --data-source csv --csv-path data/markets/BTCUSDT_1h.csv
```

Чтобы сохранить результат backtest в `results/`:

```bash
python main.py --mode backtest --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv --save-results
```

Файл сохраняется как `results/backtest_<strategy>_<symbol>_<timestamp>.json` и содержит `config`, `strategy_name`, `risk_settings`, `metrics`, `trades`, `rejected_trades`, `final_account_state`, `equity_curve`, `drawdown_curve`.

Compare mode прогоняет один и тот же mock history по всем стратегиям и печатает JSON-сравнение:

```bash
python main.py --mode compare --symbol BTCUSDT --data-source csv --csv-path data/BTCUSDT_1h.csv
python main.py --mode compare --symbol BTCUSDT --data-source csv --csv-path data/BTCUSDT_1h.csv --save-results
```

Multi-dataset compare прогоняет все registered rule-based strategies по CSV в `data/markets/`:

```bash
python main.py --mode compare --data-dir data/markets
```

Validation pipeline поддерживает два аналитических режима:

- `paper` - текущие строгие правила, используемые по умолчанию.
- `research` - только для анализа: настройки берутся из `research_config.yaml`, используются более мягкий volume filter multiplier, larger walk-forward windows и timeframe-aware minimum trades.

```bash
python main.py --mode compare --data-dir data/markets --validation-mode research
python main.py --mode walk_forward --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/markets/BTCUSDT_1h.csv --validation-mode research
python main.py --mode select_candidate --data-dir data/markets --validation-mode research
```

Research mode не разрешает live trading, не меняет `RiskManager`, не меняет crypto spot rules и не предназначен для исполнения сделок.

Compare report также добавляет strategy validation: `valid` и `reason`. Стратегия считается valid только если `number_of_trades >= 20`, `max_drawdown <= 20%`, `net_pnl_percent > 0`, walk-forward stable, и rejected trades count не слишком большой. Если сделок меньше 20, причина будет `"too few trades"`.

При `--save-results` compare сохраняет `results/compare_<symbol>_<timestamp>.json` с полями `config`, `execution_config`, `risk_settings`, `strategies_results`, `best_valid_strategy`, `warnings`. Если valid стратегий нет, `best_valid_strategy` будет `null`, а `warnings` содержит `"no valid strategies"`.

Safe EMA parameter sweep перебирает только фиксированную сетку `fast_ema = 5, 10, 20` и `slow_ema = 30, 50, 100`, оставляет только пары `fast_ema < slow_ema`, для каждого варианта запускает backtest и walk-forward, применяет strategy validation rules и сортирует результат по `net_pnl_percent`. Это research report, не оптимизация по одному участку:

```bash
python main.py --mode sweep --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
```

Sweep report показывает `fast_ema`, `slow_ema`, `net_pnl_percent`, `max_drawdown`, `number_of_trades`, `walk_forward_stable`, `valid`, `reason`.

### Strategy parameter research

`research/sweep_engine.py` запускает offline parameter research для `rsi_mean_reversion`, `bollinger_bands` и `breakout`. Для каждого фиксированного варианта он обязан выполнить backtest, walk-forward и multi-dataset robustness, а затем применяет действующие validation rules. Это не selection по одному PnL: кандидат valid только при достаточном числе сделок, положительном net PnL, стабильном walk-forward и успешной robustness-проверке.

Поддерживаемые фиксированные параметры: RSI `period`, `oversold`, `overbought`; Bollinger `period`, `stddev_multiplier`; Breakout `lookback`, `atr_multiplier`. Breakout использует ATR multiplier для stop-loss и risk-bounded position size.

Пример программного запуска только по локальным CSV:

```python
from research.sweep_engine import run_strategy_parameter_research

results, report_path = run_strategy_parameter_research(
    "rsi_mean_reversion",
    "BTCUSDT",
    "data/markets",
)
```

Каждый запуск сохраняет `results/strategy_research_<timestamp>.json`. У каждого варианта есть `strategy`, `params`, `average_pnl` (average net PnL percent across datasets), `drawdown`, `trades`, `robustness_score` и `valid`, а также причина и статусы walk-forward/robustness. Research module не создает ордера, не выбирает кандидата для paper replay и не подключается к бирже.

Multi-dataset robustness testing прогоняет стратегию по всем CSV в `data/markets/`:

```bash
python main.py --mode robustness --strategy ema_crossover --data-dir data/markets
```

Имена файлов вида `BTCUSDT_1h.csv`, `ETHUSDT_1h.csv`, `SOLUSDT_1h.csv`, `BTCUSDT_4h.csv` используются для извлечения `symbol` и `timeframe`. Каждый dataset проходит CSV validation, backtest, walk-forward и strategy validation.

Robustness report показывает по каждому dataset: `dataset`, `symbol`, `timeframe`, `strategy`, `net_pnl_percent`, `max_drawdown`, `number_of_trades`, `winrate`, `walk_forward_stable`, `valid`, `reason`.

Общий итог содержит `datasets_tested`, `valid_datasets_count`, `invalid_datasets_count`, `average_net_pnl_percent`, `worst_drawdown`, `robust`. Правило `robust`: минимум 3 датасета, valid datasets >= 60%, average net PnL > 0, worst drawdown <= 20%.

Candidate selection запускает compare/sweep/robustness checks и сохраняет отчет:

```bash
python main.py --mode select_candidate --data-dir data/markets
```

Файл сохраняется как `results/candidate_selection_<timestamp>.json`. Отчет содержит `selected_strategy`, `selected_params`, `reason`, `rejected_candidates`, `warnings`, `next_recommended_mode`. Если robust стратегий нет, `selected_strategy` будет `null`, а `next_recommended_mode` будет `report_only`. Candidate selection никогда не выбирает стратегию с `number_of_trades < 20` или `walk_forward_stable == false`.

Чтобы заморозить выбранный candidate config для следующего безопасного шага:

```bash
python main.py --mode select_candidate --data-dir data/markets --save-selected-config
```

Файл сохраняется как `config/selected_candidate.json` и содержит `strategy`, `params`, `selected_at`, `source_data_dir`, `validation_summary`, `robustness_summary`, `warnings`, `allowed_next_mode`.

Если стратегия не выбрана, `strategy` будет `null`, а `allowed_next_mode` всегда будет `report_only`. Если стратегия выбрана и одновременно проходит validation, walk-forward stability и robustness, `allowed_next_mode` может быть только `paper_replay`; live/paper-real режимы не разрешаются этим config.

Paper replay симулирует forward paper trading по CSV candle-by-candle:

```bash
python main.py --mode paper_replay --config config/selected_candidate.json --csv-path data/BTCUSDT_1h.csv --symbol BTCUSDT
```

Правила `paper_replay`: CLI запускается только через frozen `config/selected_candidate.json`, работает только с CSV, не использует интернет и live broker, на каждой новой свече стратегия получает только историческое окно до текущей свечи, все `TradeProposal` проходят через `OrderGateway` и `RiskManager`, а результат пишется в `journal_replay.jsonl`.

`paper_replay` берет `strategy` и `params` только из config. Если передать `--config` и одновременно `--strategy`, команда падает с ошибкой. Если `allowed_next_mode != "paper_replay"` или `strategy` в config равен `null`, replay запрещен.

Каждая запись `journal_replay.jsonl` содержит `strategy`, `params`, `config_path`, `config_selected_at`. Итоговый report содержит те же config metadata и `warning`, если `--csv-path` указывает на файл вне `source_data_dir` из frozen config.

Итоговый отчет содержит `symbol`, `strategy`, `params`, `config_path`, `config_selected_at`, `warning`, `starting_balance`, `ending_balance`, `net_pnl`, `net_pnl_percent`, `filled_orders`, `rejected_orders`, `hold_count`, `max_drawdown`, `final_positions`, `journal_path`.

Walk-forward backtest делит историю на последовательные train/test окна и проверяет стабильность стратегии:

```bash
python main.py --mode walk_forward --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
```

Отчет содержит `train_period`, `test_period`, `pnl_train`, `pnl_test`, `max_drawdown_test`, `winrate_test`, `stable`. Если стратегия хорошо работает только на одном участке, но плохо на остальных, итоговый `stable` будет `false`.

Journal report:

```bash
python main.py --mode report --journal journal.jsonl
```

Отчет по журналу печатает JSON: `total_decisions`, `filled_orders`, `rejected_orders`, `hold_count`, `total_paper_pnl`, `symbols_traded`, `average_risk_percent`, `max_position_notional`, `last_5_decisions`.

## Backtest CLI

```bash
python backtest.py --symbol BTCUSDT --timeframe 1h --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
python backtest.py --symbol BTCUSDT --timeframe 1h --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv --save-results
```

Backtest печатает JSON-отчет: `starting_balance`, `ending_balance`, `pnl`, `pnl_percent`, `number_of_trades`, `winrate`, `max_drawdown`, `rejected_trades_count`, `final_positions`.

## CSV historical data

Исторические свечи можно хранить в `data/`. CSV должен иметь заголовок:

```csv
timestamp,open,high,low,close,volume
2026-01-01T00:00:00+00:00,100,101,99,100.5,12345
```

Правила валидации: все колонки обязательны, `NaN` запрещен, цены должны быть `> 0`, `volume >= 0`, OHLC должен быть согласован (`high` не ниже `open/close/low`, `low` не выше `open/close/high`), timestamps строго отсортированы по возрастанию, duplicate timestamps запрещены, минимум 100 свечей.

Примеры запуска:

```bash
python main.py --mode backtest --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
python main.py --mode compare --symbol BTCUSDT --data-source csv --csv-path data/BTCUSDT_1h.csv
python main.py --mode walk_forward --symbol BTCUSDT --strategy ema_crossover --data-source csv --csv-path data/BTCUSDT_1h.csv
```

Если CSV плохой, команда завершится с понятной `ValueError`.

Backtest использует realistic execution model:

- сигнал на текущей свече исполняется после `latency_bars`, по умолчанию на следующей свече;
- BUY исполняется по цене хуже рынка: `price + slippage + half_spread`;
- SELL исполняется по цене хуже рынка: `price - slippage - half_spread`;
- комиссия списывается с каждой сделки;
- trades сохраняют `signal_bar_index`, `execution_bar_index`, `signal_price`, `reference_price`, `execution_price`, `commission`, `slippage_cost`;
- saved results включают `equity_curve` (`timestamp`, `equity`) и `drawdown_curve` (`timestamp`, `drawdown`);
- trades включают `entry_time`, `exit_time`, `entry_price`, `exit_price`, `commission`, `slippage_cost`, `pnl`, когда round-trip можно восстановить;
- метрики включают `total_commission_paid`, `average_slippage_cost`, `gross_pnl`, `net_pnl`, `net_pnl_percent`.
- anti-lookahead rule: стратегия получает только префикс истории `candles[:current_index]`; будущие свечи в `generate_signal()` не передаются.

## Feature Research

`feature_report` рассчитывает только historical market features из локального CSV и не вызывает стратегию, `OrderGateway`, broker или paper execution. Последний доступный срез сохраняется как `results/features_<symbol>_<timestamp>.json`.

```bash
python main.py --mode feature_report \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv
```

Report включает: trend `ema_distance` (EMA50 vs EMA200), `ema_slope` (EMA50 one-bar slope), `adx`; momentum `roc` (14 bars), `returns_7`, `returns_30`; volatility `atr_percent` (ATR14), `rolling_volatility` (20 returns), `candle_range_percent`; volume `volume_sma_ratio` и `volume_zscore` (20 bars). Недостаточная история записывается как `null`, а не заполняется будущими свечами.

### Feature-Based Strategy Gating

Перед созданием proposal стратегии получают feature gate только на историческом окне. `ema_crossover` и `macd_strategy` разрешены при `ADX > 20` и положительном `ema_slope`. `rsi_mean_reversion` и `bollinger_bands` разрешены при `ADX < 25` и режиме не `HIGH_VOLATILITY`. `breakout` требует `volume_zscore > 1` и текущий `atr_percent` выше среднего ATR percent предыдущих баров.

Не прошедший gate возвращает `HOLD` до создания `TradeProposal`. В `journal_replay.jsonl` такая запись содержит `hold_reason` с причиной feature filter rejection. Gate не исполняет ордера и не заменяет `RiskManager` или `OrderGateway`.

### Strategy Attribution

`strategy_report` запускает offline attribution на local CSV, применяет existing next-bar execution model и сохраняет `results/strategy_report_<timestamp>.json`. Все proposals по-прежнему идут только через `OrderGateway` и `RiskManager`.

```bash
python main.py --mode strategy_report \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv \
  --strategy ema_crossover
```

Report содержит `total_signals`, `hold_count`, `hold_reasons`, `blocked_by_feature_filter`, `executed_trades`, `win_count`, `loss_count`, `pnl_by_market_regime`, `pnl_by_timeframe` и `average_trade_duration_seconds`. Closed-trade PnL относится к market regime в момент входа; открытые позиции не считаются win/loss до закрытия.

### Feature Gate Sensitivity Research

`filter_sweep` исследует фиксированную сетку feature gates: ADX threshold `15, 20, 25, 30`, volume multiplier `0.8, 1.0, 1.2`, ATR volatility threshold `0.5, 1.0, 1.5`. Для каждой комбинации выполняются backtest, walk-forward, attribution и robustness на локальных CSV.

```bash
python main.py --mode filter_sweep \
  --strategy ema_crossover \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv
```

Результат сохраняется как `results/filter_sweep_<timestamp>.json`. Каждая строка содержит `trades_count`, `stability`, `robustness`, `net_pnl`, filled trades, signal/HOLD counts и причины HOLD. Sweep не выбирает параметр по PnL: `valid` требует обычной validation и robustness; сортировка приоритизирует validity, robustness, stability, trades и drawdown, используя PnL только как tie-breaker.

### Market Regime Strategy Router

`regime_report` анализирует historical CSV candle-by-candle и выбирает только допустимые strategy candidates, без создания proposals в broker и без отправки ордеров. При `TREND` (`ADX > 25` и positive EMA slope) разрешены `ema_crossover` и `macd_strategy`. При `RANGE` (`ADX < 20`) разрешены `rsi_mean_reversion` и `bollinger_bands`. При `HIGH_VOLATILITY` (ATR percent `>= 1.5%`) разрешена только `HOLD`. Значения между trend/range порогами считаются `TRANSITION` и также не разрешают стратегии.

```bash
python main.py --mode regime_report \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv
```

Report сохраняется как `results/regime_report_<timestamp>.json` и содержит `regime_distribution`, `strategy_chosen`, `blocked_strategies`, `expected_trades` и `hold_reasons`. `expected_trades` означает количество rule-based `TradeProposal` в router analysis; это не исполненные paper orders.

### Regime Router Backtest

`regime_backtest` проверяет router с realistic next-bar paper execution. На каждой свече router определяет режим, запускает только разрешенные strategies и передает полученный `TradeProposal` в `OrderGateway`; `HIGH_VOLATILITY` и `TRANSITION` дают только HOLD. Никакие реальные ордера не создаются.

```bash
python main.py --mode regime_backtest \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv
```

Отчет сохраняется как `results/regime_backtest_<timestamp>.json` и включает `total_trades`, `net_pnl`, `max_drawdown`, `pnl_by_regime`, `trades_by_strategy`, `hold_by_regime`, `regime_distribution` и `equity_curve`.

### Regime Attribution

`regime_attribution` читает JSON journal, сохраненный `regime_backtest`, и не запускает стратегии или ордера. Для каждого `TREND`, `RANGE`, `HIGH_VOLATILITY` и `TRANSITION` он показывает closed trade count, strategies used, trades per strategy, winrate, net PnL, average PnL per trade, regime-local max drawdown и average HOLD-run duration.

```bash
python main.py --mode regime_attribution \
  --journal results/regime_backtest_<timestamp>.json
```

Аналитика сохраняется как `results/regime_attribution_<timestamp>.json`. PnL закрытой сделки относится к режиму в момент входа и к стратегии, которая открыла position.

### Trade Lifecycle Analytics

`trade_lifecycle` читает closed trades из JSON report `regime_backtest` и не запускает strategies или orders. Для каждой сделки он показывает `entry_time`, `exit_time`, `duration_seconds`, entry/exit prices, PnL, regime, strategy, MAE и MFE в процентах от execution entry price. MAE использует минимальный low, а MFE максимальный high между execution entry и exit candles.

```bash
python main.py --mode trade_lifecycle \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/trade_lifecycle_<timestamp>.json` и также содержит средние duration, MAE и MFE по всем закрытым сделкам.

### Exit Analysis

`exit_analysis` читает lifecycle fields из JSON report `regime_backtest` и не запускает strategies или orders. Exit классифицируется как `stop_loss`, когда execution exit price не выше entry stop-loss; как `take_profit`, когда она не ниже entry take-profit; иначе как `reversal`. `positive_mfe_before_losing` считает убыточные сделки с положительным MFE. `missed_profit_count` считает сделки, у которых intratrade MFE достиг take-profit уровня, но exit не был take-profit.

```bash
python main.py --mode exit_analysis \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/exit_analysis_<timestamp>.json` и содержит эти метрики по strategy и по `TREND`, `RANGE`, `HIGH_VOLATILITY`.

### Position Management Research

`position_management` выполняет offline posthoc research по recorded lifecycle paths и не меняет strategy logic или не создает orders. Он перебирает ATR trailing stop multipliers `1.0, 1.5, 2.0, 3.0`, maximum holding periods `10, 20, 50, 100` candles и break-even activation `+1%, +2%` (32 комбинации). Модель может только перенести exit раньше исходного lifecycle exit.

```bash
python main.py --mode position_management \
  --journal results/regime_backtest_<timestamp>.json
```

Результат сохраняется как `results/position_management_<timestamp>.json` с total trades, winrate, net PnL, max drawdown, average MAE/MFE, profit factor и `stability`. Stability требует не менее 20 closed trades, positive net PnL и max drawdown не выше 20%; PnL не используется как единственный критерий.

### Monte Carlo Robustness

`monte_carlo` читает closed trade PnL из `regime_backtest` JSON и строит 1000 deterministic random sequence permutations. Он не запускает strategies, execution model или orders.

```bash
python main.py --mode monte_carlo \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/monte_carlo_<timestamp>.json` и содержит median/mean/worst/best PnL, probability positive/loss и min/p05/median/mean/p95/max max-drawdown distribution. При permutations без replacement итоговая PnL одинакова для всех сценариев; распределение max drawdown показывает риск порядка сделок.

### Entry Quality Research

`entry_quality` читает entry snapshots из JSON report `regime_backtest` и не запускает strategies или orders. Для каждого filled long entry он показывает timestamp, strategy, regime и features на signal candle: ADX, EMA slope/distance, RSI, ATR percent и volume z-score. Post-entry outcomes измеряются после 5, 10 и 20 следующих candles: close return, MFE и MAE.

```bash
python main.py --mode entry_quality \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/entry_quality_<timestamp>.json`. Недостаточная история после entry для заданного horizon записывается как `null` и не заменяется будущими данными за пределами окна.

### Signal Quality Research

`signal_quality` читает все recorded `TradeProposal` signals из JSON report `regime_backtest`, включая предложения, которые не были filled. Для каждого signal сохраняются strategy, timestamp, regime, ADX, EMA slope/distance, RSI, ATR percent и volume z-score. Score `0-10` состоит из trend score (ADX + EMA slope, 0-3), volume confirmation (0-2), regime suitability (0-3) и volatility normality (0-2).

```bash
python main.py --mode signal_quality \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/signal_quality_<timestamp>.json` и агрегирует buckets `0-2`, `3-5`, `6-8`, `9-10`: number of signals, filled trades, directional average future return через 5/20 candles и MFE/MAE для каждого horizon.

### Market Timing Research

`entry_timing` читает recorded `TradeProposal` timing snapshots из JSON report `regime_backtest`, не запускает strategies и не создает orders. Перед signal рассчитываются distance from EMA50/EMA200, bars since EMA50/EMA200 bullish cross, current trend duration, ADX и ATR percent. Если completed EMA cross еще не наблюдался, trend age использует текущую bullish trend duration.

```bash
python main.py --mode entry_timing \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/entry_timing_<timestamp>.json` и группирует trend age `0-10`, `10-30`, `30-50`, `50+` candles. Для каждого bucket рассчитываются signals, fills, directional average return за 5/20 candles и MFE/MAE по обоим horizons.

### Regime Transition Research

`regime_transition` читает recorded `TradeProposal` transition context из JSON report `regime_backtest` и не запускает strategies или orders. Каждый signal хранит previous/current regime, bars since transition и один из `RANGE_TO_TREND`, `TREND_TO_RANGE`, `HIGH_VOLATILITY_TO_TREND`, `HIGH_VOLATILITY_TO_RANGE`, если переход наблюдался. Для переходов, не имеющих достаточной предыстории, тип остается `null` и сигнал консервативно относится к bucket `20+`.

```bash
python main.py --mode regime_transition \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/regime_transition_<timestamp>.json` и группирует entries в `0-5`, `5-20`, `20+` candles after transition с fills, directional 5/20-candle return и MFE/MAE.

### Opportunity Analysis Research

`opportunity_analysis` исследует исторический CSV и не создает ордера. LONG opportunity определяется, когда close через 20 свечей выше текущего close более чем на `--opportunity-threshold` процентов (по умолчанию `2.0`). На каждой свече rule-based router и разрешенные им стратегии получают только исторический префикс данных. `actual_signals` означает BUY `TradeProposal`; `filled_trades` означает такой сигнал, для которого есть следующая свеча, поэтому он был бы доступен для paper execution. Это не вызов `BrokerPaper` или `OrderGateway`.

```bash
python main.py --mode opportunity_analysis \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv \
  --opportunity-threshold 2.0
```

Отчет сохраняется как `results/opportunity_analysis_<timestamp>.json`. В `records` для каждой исторической свечи сохраняются future returns за 5/10/20 candles и контекст regime/features. Также отчет показывает overall count и группировку по market regime, timeframe, ADX bucket, volume z-score bucket и типу trend transition. `missed_opportunities` считает opportunities без BUY signal на той же исторической свече.

### Transition Entry Research

`transition_entry` сравнивает ограниченные paper-only варианты входа в `TRANSITION` на основе CSV, указанного в журнале `regime_backtest`. Он не изменяет стратегии: adapter передает существующим EMA/MACD исследовательский `TREND` context только когда variant-router подтвердил условия. Все simulated fills по-прежнему проходят существующие `OrderGateway` и `RiskManager`; live mode отсутствует.

```bash
python main.py --mode transition_entry \
  --journal results/regime_backtest_<timestamp>.json
```

Нужен journal, созданный после добавления `source_csv_path`; для старого файла сначала повторно запустите `regime_backtest --csv-path ...`. Отчет `results/transition_entry_<timestamp>.json` содержит baseline (`TRANSITION = HOLD`) и три варианта: ADX rising + positive EMA slope, тот же фильтр с `volume_zscore > 0`, и последний вариант с BUY position size multiplier `0.5`. Для каждого сохраняются paper backtest metrics, MAE/MFE, regime attribution и independent 60/40 walk-forward comparison. Это исследование, а не изменение paper strategy или candidate-selection rules.

### Trend Confirmation Delay Research

`trend_confirmation_delay` исследует только задержку BUY после перехода `RANGE_TO_TREND`, не меняя rule-based strategy logic. Baseline принимает BUY сразу после разрешения `TREND`; variants ждут 3 или 5 candles после перехода, либо требуют ADX > 25, positive EMA slope, close above EMA50 и positive volume z-score. SELL proposals не задерживаются.

```bash
python main.py --mode trend_confirmation_delay
```

Без аргументов команда использует последний `results/regime_backtest_*.json`; источник можно зафиксировать через `--journal results/regime_backtest_<timestamp>.json`. Отчет `results/trend_confirmation_delay_<timestamp>.json` содержит trades, winrate, PnL, drawdown, MAE/MFE, 60/40 walk-forward stability и regime attribution для каждого варианта. Все fills остаются paper-only и проходят текущие `OrderGateway` и `RiskManager`.

### Exit Optimization Research

`exit_optimization` использует только `closed_trade_records.price_path` из существующего regime-backtest journal. Это post-hoc lifecycle research: точки входа и стратегии остаются прежними, а новые orders не создаются. Baseline сохраняет recorded exit; варианты сравнивают trailing stop `1.5 ATR` и `2 ATR`, break-even stop после `+1%`, и partial exit `50%` при `+2%` с сохранением оставшейся половины до recorded exit.

```bash
python main.py --mode exit_optimization \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/exit_optimization_<timestamp>.json` и содержит trades, winrate, PnL, max drawdown, profit factor, MAE/MFE, chronological 60/40 walk-forward stability и PnL/trades by entry regime для всех вариантов.

### Entry Threshold Research

`entry_threshold` читает captured BUY `TradeProposal` records из `signal_quality_records` и сопоставляет только already-filled BUY signals с recorded closed trades той же strategy. Он не вызывает strategies, не меняет entry/exit logic и не создает orders. Варианты исследуют: `ADX > 30` + `volume_zscore > 1` + positive EMA slope; `ADX > 25` + positive volume z-score + positive EMA slope; `ADX > 20`; и отсутствие дополнительных фильтров.

```bash
python main.py --mode entry_threshold \
  --journal results/regime_backtest_<timestamp>.json
```

Отчет сохраняется как `results/entry_threshold_<timestamp>.json` и содержит filtered signals, filled/closed trades, winrate, net PnL, drawdown, MAE/MFE, profit factor, chronological 60/40 walk-forward stability и PnL/trades by entry regime. Filled BUY без recorded close не искажают realized PnL.

### Multi-Asset Validation Research

`multi_asset_validation` автоматически читает все `SYMBOL_TIMEFRAME.csv` из `data/markets/` и проверяет EMA crossover, MACD, RSI mean reversion, Bollinger Bands, breakout, trend pullback и adaptive trend following. Для каждой dataset/strategy комбинации выполняются existing paper-only backtest и walk-forward; robustness рассчитывается один раз для каждой стратегии по всему набору CSV и прикладывается ко всем ее dataset rows. Также сохраняются point-in-time entry quality и signal-quality attribution: стратегия получает только historical prefix, а future returns/MFE/MAE используются лишь после генерации BUY signal для исследования качества.

```bash
python main.py --mode multi_asset_validation --data-dir data/markets
```

Отчет сохраняется как `results/multi_asset_validation_<timestamp>.json`. Кандидат не считается successful при fewer than 50 trades, unstable walk-forward, non-robust strategy или max drawdown above 20%. Сортировка консервативная: valid/stable/robust статус, число сделок и drawdown имеют приоритет над net PnL; прибыль используется только как tie-breaker.

### Portfolio Validation Research

`portfolio_validation` строит historical CSV portfolios из комбинаций strategy, asset и timeframe. Для каждой individual combination сохраняются trades, winrate, net PnL, drawdown, profit factor, walk-forward/robustness, duration и MAE/MFE. Для каждого timeframe создаются multi-asset sleeves одной стратегии и mixed-strategy sleeves. Исследование использует только existing paper-only backtest results, включая commission/slippage и RiskManager limits; оно не добавляет execution path, live trading или API keys.

```bash
python main.py --mode portfolio_validation --data-dir data/markets
```

Каждый portfolio starts with `10_000 USDT` and divides capital equally between sleeves. Поскольку каждый sleeve проходит существующий `RiskManager` с max position `10%`, сумма потенциальных одновременных позиций ограничена `10%` стартового portfolio. Отчет `results/portfolio_validation_<timestamp>.json` содержит portfolio metrics, allocation contribution, equity-curve correlations, strategy similarity flags и profit/risk concentration checks. Portfolio candidate valid только при at least 100 trades, stable walk-forward, robust allocations, drawdown <=20% и contribution одного актива <=70% positive profit. Portfolio validation is research-only and does not enable live trading.

### Market Microstructure Research

`market_microstructure` анализирует локальный historical CSV candle-by-candle и не создает orders. Для каждой свечи сохраняются liquidity (volume, SMA ratio, z-score, percentile), volatility (ATR%, rolling volatility, body/wicks/range) и market-efficiency features. Для каждого generated `TradeProposal` сохраняется liquidity/volatility state, market condition, regime и environment score `0-10` с bucket. Стратегия получает только historical prefix; 5/20-candle returns, MFE и MAE вычисляются после signal только как research labels.

```bash
python main.py --mode market_microstructure \
  --symbol BTCUSDT \
  --csv-path data/markets/BTCUSDT_1h.csv
```

Отчет `results/market_microstructure_<timestamp>.json` содержит total candles/signals, execution-eligible signals (`filled_trades`), groupings по liquidity и volatility, а также strategy/regime performance по `TRENDING`, `RANGING`, `CHOPPY`. `average_pnl_proxy_percent` означает future 20-candle directional return и не является исполненным PnL. Market microstructure research is historical CSV-only and does not enable live trading.

### Reproducible Benchmark

Перед benchmark выполните audit local CSV:

```bash
.venv/bin/python tools/audit_market_data.py --data-dir data/markets --output results/data_audit.json
.venv/bin/python tools/build_research_dataset.py --data-dir data/markets
.venv/bin/python main.py --mode benchmark_suite --data-dir data/markets
```

Builder загружает только spot OHLCV через existing historical downloader, не использует API keys, orders или broker. Он пишет временный CSV, валидирует его и только затем атомарно переименовывает в `data/markets/SYMBOL_TIMEFRAME.csv`; ошибки отдельных datasets сохраняются в `data/markets/manifest.json` без остановки остальных. `dataset_split` делит eligible datasets строго по времени: development 60%, validation 20%, untouched holdout 20%, с минимум 500 candles в каждом segment.

`benchmark_suite` не добавляет стратегии/правила и не импортирует sweep/filter research. Он фиксирует pre-holdout config с SHA256, выполняет development/validation до holdout и использует holdout только с этим frozen config. Candidate требует validation >=50 trades, holdout >=20 trades, positive validation/holdout PnL, drawdown <=20%, stable walk-forward, robustness, минимум 3 positive holdout datasets и <=70% profit concentration. При отсутствии candidate `next_recommended_mode` остается `report_only`; paper replay автоматически не запускается. Артефакты: `results/benchmark_suite_<timestamp>.json`, `results/dataset_splits_<timestamp>.json`, `results/benchmark_config_<timestamp>.json`, `results/data_audit.json` и `BENCHMARK_STATUS.md`.

Текущие rule-based implementations рассчитывают индикаторы по полному historical prefix на каждом bar. Поэтому benchmark фиксирует reproducible `500`-candle evaluation window внутри каждого full chronological segment и один `300/200` walk-forward fold. Полные 60/20/20 границы остаются в split manifest; development и validation используют начало своих сегментов, а holdout использует последние 500 candles своего untouched segment. Это не является parameter tuning и не изменяет validation thresholds.

### Optional Freqtrade Migration

Freqtrade migration is optional infrastructure, not a replacement for the legacy engine. It is restricted to historical download/backtesting/research and a future guarded dry-run path. The pinned image is `freqtradeorg/freqtrade:2026.5.1`; compose defaults to `--help`, has no auto-restart and never starts a bot.

```bash
.venv/bin/python tools/freqtrade_safe.py backtesting --strategy EmaCrossoverStrategy
```

The wrapper validates `freqtrade_user_data/configs/config.paper.json` before invoking Docker: `dry_run=true`, spot-only, empty credentials, static USDT pair allowlist, derivative/leveraged blacklist, FreqAI disabled and no remote pairlist. Docker verification, historical download, backtests, lookahead and recursive analysis have completed, but dry-run remains rejected. `freqtrade_data_compare` reads native Freqtrade Feather data without changing it or legacy CSV. Dual-engine equivalence and RiskManager equivalence remain blocking gaps. See `FREQTRADE_MIGRATION_PLAN.md`, `FREQTRADE_MIGRATION_STATUS.md`, `FREQTRADE_STRATEGY_MAPPING.md` and `FREQTRADE_RISK_GAPS.md`.

## Strategy research

Стратегии живут в `strategies/` и реализуют единый интерфейс:

```python
generate_signal(bars, account_state) -> TradeProposal | Signal.HOLD
```

Стратегии не исполняют сделки. Они только возвращают `TradeProposal` или `HOLD`; backtest передает все предложения через `OrderGateway` и `RiskManager`.

Перед `generate_signal()` backtest и paper replay вычисляют market regime только на историческом префиксе свечей:

- `TREND` определяется через ADX и EMA slope.
- `RANGE` используется для бокового рынка.
- `HIGH_VOLATILITY` определяется через ATR percent и запрещает новые сделки.
- Volume confirmation требует, чтобы текущий volume был не ниже SMA20 volume; иначе signal становится `HOLD`.

Regime rules:

- `ema_crossover`, `macd_strategy`, `trend_pullback` и `adaptive_trend_following` работают только в `TREND`.
- `rsi_mean_reversion` и `bollinger_bands` работают только в `RANGE`.
- `HIGH_VOLATILITY` возвращает `HOLD` для этих стратегий.

Доступные стратегии:

- `ema_crossover`
- `rsi_mean_reversion`
- `macd_strategy`
- `bollinger_bands`
- `breakout`
- `trend_pullback`
- `adaptive_trend_following` - long-only trend following: close выше EMA200, EMA50 выше EMA200, ADX выше 20 и volume не ниже SMA20; выход ниже EMA50 или по ATR trailing stop.
- `buy_and_hold`

## Тесты

```bash
python -m pytest
```

## Safety

- `.env.example` не содержит реальных ключей.
- `BrokerPaper(mode="LIVE")` выбрасывает `ValueError`.
- В проекте нет live trading mode и нет кода отправки реальных ордеров.
- Все paper-ордера идут через `OrderGateway`.
- Backtest/compare также исполняют предложения стратегий только через `OrderGateway`.
- Walk-forward использует тот же paper-only backtest path и не оптимизирует параметры по test-окнам.
- `BrokerPaper.submit_order()` не принимает сырые аргументы вида `symbol, side, quantity, price`; нужен только `ApprovedOrder`.
- `ApprovedOrder` создается `RiskManager` только после проверок stop-loss, риска 1%, max position 10%, дневного лимита убытка и запрета плеча.
- `ApprovedOrder` immutable и подписан HMAC-подписью; изменение proposal после approval делает ордер невалидным.
- Реальные API-ключи и broker credentials запрещены; `.env.example` содержит только paper-настройки.
