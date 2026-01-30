---
name: exchange-connector
description: "交易所连接与统一交易接口封装。用于读取余额/持仓、下单、撤单、查订单、查成交等交易指令，并将交易所差异封装在 skill 内，对外提供统一接口；至少支持 Bitget。"
---

# 交易所连接（统一接口）

## 目标

- 提供统一的交易所操作接口：读余额、读持仓、下单、撤单、查订单、查成交
- 把交易所差异隐藏在 skill 内，外层策略不关心具体交易所细节
- 至少落地 Bitget 适配

## 快速流程

1) 明确交易所与账户类型（现货/合约）
2) 校验所需字段与权限
3) 通过统一接口完成操作
4) 返回标准化结果结构

## 统一接口规范

必须提供以下方法签名，并保持返回字段一致：

- `get_account_info()`：余额、可用保证金、风险率
- `get_positions()`：现货/合约持仓、均价、未实现盈亏
- `place_order(symbol, side, type, qty, price?, reduce_only?, leverage?)`
- `cancel_order(order_id)` / `cancel_all(symbol?)`
- `get_open_orders(symbol?)`
- `get_fills(symbol?, since?)`

### 标准化返回建议

尽量统一为以下字段，便于策略层消费：

- 余额：`asset`, `total`, `available`, `used`
- 持仓：`symbol`, `side`, `qty`, `entry_price`, `mark_price`, `upl`, `upl_pct`
- 订单：`order_id`, `symbol`, `side`, `type`, `qty`, `price`, `status`, `filled_qty`
- 成交：`fill_id`, `order_id`, `symbol`, `side`, `qty`, `price`, `fee`, `timestamp`

## 交易所差异封装

建立适配层，统一处理以下差异：

- 市场类型：现货/USDT 本位合约/币本位合约  
- 杠杆与保证金：逐仓/全仓，风险率口径不同  
- 订单类型与参数：限价/市价/只减仓/触发单  
- 精度与最小下单量：价格与数量精度、最小名义价值  
- 速率限制与重试：遇到频率限制要做退避重试

若交易所字段不足，需在统一层补齐或返回 `null` 并说明原因。

## Bitget 适配要求

至少实现 Bitget 的完整通路：

- 账户/持仓查询接口  
- 下单、撤单、查询开放订单、查询成交  
- 统一错误码与异常提示

若需要扩展其它交易所，新增适配器并复用统一接口与返回结构。

## Bitget 字段映射与接口说明

当需要实现 Bitget 适配或排查字段不一致时，阅读 `references/bitget.md`。

## 统一行为约束

- 所有方法返回结构必须包含 `ok` 与 `error` 字段，`ok` 为布尔值
- 失败时 `error` 返回结构化信息：`code`, `message`, `retryable?`
- 订单与成交时间戳统一为毫秒时间戳
- `side` 统一为 `buy`/`sell`，`type` 统一为 `market`/`limit`
- `qty`、`price` 统一为字符串或高精度数值类型，避免浮点精度损失

## 参数处理与校验

- `symbol` 统一为交易所规范符号（如 `BTCUSDT` 或 `BTC/USDT`），内部适配器负责映射
- 限价单必须带 `price`，市价单禁止传 `price`
- `reduce_only` 仅在合约场景生效，现货应忽略或返回明确错误
- `leverage` 仅在合约场景生效，缺省时使用交易所默认

## 统一返回示例

保持轻量，必要时可补充字段，但不删除标准字段：

```json
{
  "ok": true,
  "data": {
    "order_id": "123",
    "symbol": "BTCUSDT",
    "side": "buy",
    "type": "limit",
    "qty": "0.01",
    "price": "50000",
    "status": "open",
    "filled_qty": "0"
  },
  "error": null
}
```

## 输出要求

当用户发出交易指令时：

- 明确解析后的参数
- 说明将调用的统一接口
- 返回标准化结果或失败原因
- 明确任何无法执行的前置条件（权限、参数缺失、精度不符）
