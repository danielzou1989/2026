---
name: bitget-account-login
description: "Bitget 个人账户登录与查询摘要/余额/持仓。用户请求“查询我的账户/查看我的持仓/余额/资产/账户信息”等时使用，自动加载 personkey.env 凭证并调用账户信息接口。"
---

# Bitget 个人账户登入与查询

## 目标

- 读取本地 `personkey.env` 凭证并完成 Bitget 账户查询
- 默认返回摘要/余额/持仓信息，不输出任何密钥或完整敏感信息

## 凭证来源

- 凭证文件路径：`skills/exchange-connector/personkey.env/personkey.env`
- 必需环境变量：
  - `BITGET_API_KEY`
  - `BITGET_API_SECRET`
  - `BITGET_API_PASSPHRASE`
  - `BITGET_API_BASE_URL`

## 安全约束（必须遵守）

- 绝不打印或回显 `API_KEY/SECRET/PASSPHRASE`
- 如需确认加载成功，仅输出“已加载/缺失”或掩码长度

## 执行流程

1) 加载凭证文件（dotenv 或等价方式），校验必需变量存在
2) 优先查找并复用已有统一接口（如 `get_account_info()` / `get_positions()`）
3) 若无统一接口，则直接调用 Bitget REST API：
   - 账户摘要：`GET /api/v2/mix/account/accounts?productType=USDT-FUTURES`
   - 持仓列表：`GET /api/v2/mix/position/all-position?productType=USDT-FUTURES`
4) 将返回字段整理为摘要/余额/持仓列表，保持字段清晰与可读

## 返回内容（默认）

- 账户摘要：账户权益、可用余额、未实现盈亏、冻结等
- 持仓列表：交易对、方向、数量、开仓均价、未实现盈亏、杠杆

## 交互规范

- 若用户未说明业务线（USDT/COIN/USDC），先询问或使用默认 `USDT-FUTURES`
- 用户只要提出“查询账户/查看持仓/余额/资产”，就触发本技能并执行查询
