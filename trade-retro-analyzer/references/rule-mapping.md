# 量化指标 → 参数调整建议（规则表）

## 使用方式
- 以 `retro_summary.py` 的输出为主（overall + grouped）。
- 先看总体，再看分组（symbol/direction/session/vol_bucket 等）。
- 满足阈值则生成参数调整建议，建议落到 `risk_config.json` 或具体策略文件。

## 风险/止损相关
- **expectancy < 0 且 mae_mean 高** → 收紧止损  
  - `stop_loss.default_pct` 下调 10%～20%
- **mae_mean 低但 avg_loss 高** → 说明亏损集中在突发波动  
  - 启用/加严 `trailing_activation` 与 `trailing_distance`
- **max_drawdown 超阈值** → 降低 `position_sizing.max_position_size` 或 `base_position_size`

## 止盈/收益相关
- **mfe_mean 高且 pnl_net 低** → 过早止盈/未跟踪  
  - 提高 `take_profit.levels` 中后段比例或启用更紧的 trailing
- **win_rate 高但 payoff 低** → 止盈过早  
  - 小幅提高前两级 `take_profit.levels`（+0.5%～1%）

## 成本/执行相关
- **cost_ratio > 0.35** → 费用/滑点侵蚀  
  - 对应策略 `min_spread` 或 `flip_profit_target` 上调 20%～50%
  - 限制单笔 `max_single_order_value`，拆单
- **slippage 高于 fees** → 执行冲击大  
  - 降低 `order_size` 或加大 `prefer_maker` 权重

## 持仓时长相关
- **holding_mean 高且 expectancy 低** → 拿太久  
  - 收紧 `max_holding_time` 或加时间止盈/止损
- **holding_mean 低且 avg_loss 高** → 频繁止损  
  - 放宽止损或增加入场确认条件

## 头寸/方向相关
- **direction=buy 组 expectancy 低** → 增加情绪过滤或趋势确认
- **direction=sell 组 expectancy 低** → 降低空头权重或提高 entry 过滤
