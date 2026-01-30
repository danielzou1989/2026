---
name: crypto-news-sentiment-filter
description: "加密新闻情绪过滤器。用于抓取 X(Twitter)/Telegram/新闻站点的实时信息流，将新闻分类为利好/利空/FUD/噪音并打分（-1到+1），当用户需要用情绪过滤交易信号或询问“全网情绪/新闻情绪/是否否决交易”时使用。"
allowed-tools: Bash
---

# 加密新闻情绪过滤器

## 目标

- 以 1 分钟轮询、30 分钟窗口抓取新闻流
- 对每条新闻进行分类（利好/利空/FUD/噪音）并输出评分（-1 到 +1）
- 聚合形成“情绪否决”信号供交易策略参考

## 数据源与接入

### 必选 RSS 源

优先使用 RSS/公开源，不依赖需要登录的 API。

- CoinDesk（RSS）
- CoinTelegraph（RSS）
- The Block（RSS）
- Decrypt（RSS）
- CoinMarketCap News（RSS）
- CoinGecko News（RSS）
- Messari（RSS）
- Glassnode（RSS）
- CryptoQuant（RSS）
- Santiment（RSS）
- AIcoin（RSS）
- PANews（RSS）
- Odaily（RSS）
- 8BTC（RSS）
- 金色财经（RSS）

注：RSS 链接可能会变动，实际使用时先验证最新地址；清单见 `references/sources.md`。

### 获取方式（避免 403）

- 严禁使用 WebSearch / WebFetch（会触发 403）
- 通过 `curl` 直接拉取 RSS
- 若网络受限或返回 403，提示用户需要 /login 或改用本地缓存

### X(Twitter)（可选，默认关闭）

- 无官方 API key 时，使用第三方镜像（如 Nitter）RSS
- 若镜像不可用或受限，直接禁用 X 源并说明原因

### Telegram（可选，默认关闭）

- 使用公开频道为主（如需私有频道需 token/session）
- 若无稳定接入方式，保持关闭并说明

## 轮询与去重

- 轮询周期：每 1 分钟
- 窗口：过去 30 分钟
- 去重：基于 URL、标题哈希、发布时间的组合键
- 仅保留窗口内最新条目并记录来源

## 分类规则（利好/利空/FUD/噪音）

### 关键词与语义线索

- **利好**：ETF/合规/机构入场/监管明确/通过/上线/合作/资金流入/链上活跃上升
- **利空**：被禁止/被起诉/破产/黑客/大额抛售/冻结/调查/链上异常
- **FUD**：消息来源不明/传言/未证实/恐慌扩散/标题党
- **噪音**：纯价格复盘/无实质事件/营销内容/重复转载

### 来源权重建议

- 高权重：CoinDesk、The Block、Messari、Glassnode、CryptoQuant、Santiment
- 中权重：CoinTelegraph、Decrypt、CoinMarketCap、CoinGecko
- 低权重：X/Telegram/自媒体（除非多源交叉验证）

## 打分规则（-1 到 +1）

### 单条评分

1) 先判定分类（利好/利空/FUD/噪音）  
2) 计算强度：弱/中/强 → 0.3/0.6/0.9  
3) 结合来源权重（高 1.0 / 中 0.7 / 低 0.4）  
4) 得到 raw_score 并限制到 [-1, +1]

示例：

- 强利好 + 高权重：+0.9
- 弱利好 + 中权重：+0.21
- 强利空 + 高权重：-0.9
- FUD：按负向处理并额外标注 “FUD”
- 噪音：0 或接近 0

### 聚合评分

- 按 30 分钟窗口取加权平均
- 对同一事件多源重复报道仅计一次
- 输出 `sentiment_score` 与 `sentiment_label`（利好/利空/中性）

## 否决规则（示例）

- 若 `sentiment_score <= -0.4` 且技术信号为买入 → 建议否决
- 若 `sentiment_score >= +0.4` 且技术信号为卖出 → 提醒可能逆势

## 输出格式（建议）

```markdown
### 新闻情绪摘要（30min）
- 情绪评分: -0.35（偏利空）
- 分类占比: 利好 10% / 利空 45% / FUD 25% / 噪音 20%
- 是否否决买入: 是（情绪过差）

### 关键新闻
1) [来源] 标题 — 分类: 利空 — 评分: -0.7
2) [来源] 标题 — 分类: FUD — 评分: -0.4
```
