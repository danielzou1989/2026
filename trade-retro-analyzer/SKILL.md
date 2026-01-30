---
name: trade-retro-analyzer
description: Systematic review of historical trades to compute performance metrics, tag mistakes, extract lessons, and translate them into concrete strategy/config updates. Trigger when asked to复盘/回顾历史交易、总结经验、优化策略参数或规则。
---

# Trade Retro Analyzer

Concise workflow to review past trades, surface actionable insights, and feed them back into strategy rules/config.

## Inputs to request (if missing)
- Trade history with timestamps, symbol, side, entry/exit price, size, fees, pnl; preferably CSV/JSON or exchange export.
- Benchmarks: market return over holding window; target strategy rules/parameters for comparison.
- Context tags (optional): signal type, regime, execution venue, slippage model.

## Quick metrics to compute
- Win rate, avg win/loss, payoff ratio, expectancy (per trade & per unit risk), max drawdown.
- MAE/MFE: distance from entry to worst/best price during hold; flag trades where stop/take-profit placement failed.
- Holding time distribution; PnL by holding bucket (scalps vs swing).
- Slippage & fee impact: PnL before/after costs; identify pairs/time-of-day with high impact.
- Error tags: late entry, rule violation, over-size, no exit plan, widened spread.

## Analysis workflow
1) **Load & clean**: ensure numeric fields, align timestamps, drop canceled orders; derive net_pnl, return_pct, risk_pct if stop known.
2) **Segment** by regime (trend/range), symbol, signal type, time-of-day, and position direction; compute metrics per segment.
3) **Diagnose exits**: compare actual exits to ideal (e.g., hit TP/SL/timeout); count premature exits vs missed stops.
4) **Size & risk check**: compare position size to plan (e.g., account_risk_pct), flag >110% or <50% of intended.
5) **Playbook extraction**: list top positive patterns (high expectancy) and negative patterns (drawdown drivers) with examples.
6) **Action items**: convert findings into parameter tweaks or rules (see next section).

## Translating lessons to strategy/config
- Stop/Take-Profit: adjust pct, activate trailing, or add time-based exit when MFE high but realized PnL low.
- Position sizing: reduce size in regimes with high variance of returns; increase slightly in high-conviction/low-MAE segments.
- Entry filters: add spread/volatility filters, minimum liquidity thresholds.
- Execution: prefer maker when spread > fee buffer; enforce max slippage per symbol/time window.
- Playbook rules: codify “do” and “avoid” with trigger conditions; update strategy docs/config files accordingly.

## Output format
- **Summary table** of key metrics (win rate, payoff, expectancy, DD, costs impact).
- **Top 3 improvements** with specific parameter edits (file + key + new value) and rationale.
- **Playbook bullets**: pattern → rule/change → evidence (n trades, expectancy).
- **Follow-up checks**: data quality gaps, tests to run (e.g., backtest with new stops), monitoring alerts.

## Fast prompts/templates
- “Compute expectancy, win rate, payoff by symbol and direction; include cost-adjusted figures.”
- “Show MAE/MFE percentiles and how often stops/TPs were touched before exit.”
- “List the worst 10 trades by normalized loss; tag primary error causes.”
- “Propose config edits for stop_loss / take_profit / position_sizing based on findings.”

## Resources
- Formulas & examples: `references/metrics.md`
- Rule mapping table: `references/rule-mapping.md`
- Quick calculator: `scripts/retro_summary.py` (CSV/JSON)  
  - Usage: `python scripts/retro_summary.py trades.csv --group-by symbol direction`
  - Outputs JSON with overall + grouped metrics (win rate, payoff, expectancy, costs impact).
- Patch suggestions: `scripts/retro_map.py`  
  - Usage: `python scripts/retro_map.py summary.json --config high-freq-trading-system/config/risk_config.json`
  - Rules: `--rules trade-retro-analyzer/references/rule-thresholds.json`

## Mapping findings到策略/配置
- 止损/止盈：对应 `high-freq-trading-system/config/risk_config.json` 的 `stop_loss` / `take_profit` 段；策略自带默认值在 `strategies/*.py`（如 `trend_following.py`, `grid_trading.py`, `breakout_strategy.py`）。
- 仓位：`risk/position_sizer.py` 与 `config/risk_config.json` 的 `position_sizing`。
- 频控/执行：`core/rate_limiter.py`，以及策略里的 `max_holding_time`、`min_spread` 等字段。
- 提交改动时，用 patch/commit 信息里注明“依据复盘：样本 n，expectancy 提升 X，主要原因 Y”。

## Tips
- Keep SKILL.md concise; push heavy stats to on-the-fly calculations rather than storing examples here.
- When data is small, load directly; when large, ask for aggregated summaries (grouped stats) to save tokens.
- Always tie recommendations to measurable evidence (counts, expectancy) and specify the target config/strategy file to edit.
