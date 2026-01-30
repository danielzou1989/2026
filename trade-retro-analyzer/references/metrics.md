# 复盘常用统计公式与示例

## 核心指标
- **胜率**: `win_rate = wins / trades`
- **平均盈亏**: `avg_win = mean(pnl | pnl>0)`, `avg_loss = mean(|pnl| | pnl<0)`
- **赔率 (Payoff Ratio)**: `payoff = avg_win / avg_loss`
- **期望 (Expectancy)**: `expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss`
- **每笔风险期望**: 若有 `risk_amount` 或按止损距离换算，`expectancy_r = expectancy / risk_amount`
- **最大回撤 (基于累计 PnL)**: 滚动最大值与当前值之差的最小值
- **成本影响**: `pnl_gross - pnl_net = fees + slippage`
- **MAE/MFE (%)**: `(entry - min/max_during_hold) / entry` 按方向符号调整

## 分组分析建议
- 按 **symbol / direction / session(时段) / regime(趋势vs震荡) / signal_type** 分组计算上述指标。
- 对每组输出：样本数、胜率、payoff、expectancy、平均持仓时长、费用占比、滑点占比、MAE/MFE 分位数。

## 示例解读
- 若 `win_rate 40%` 但 `payoff 2.8`，策略可继续；可考虑放宽止盈或收紧止损以提升 expectancy。
- 若 `fees+slippage` 占毛利 60%，应优化执行（maker 优先、限价滑点上限、拆单）或提高最小目标价差。
- 若 `MFE 高 / 实现收益低`，说明过早止盈或未用跟踪止盈；调整 `take_profit` 或启用 `trailing`.
