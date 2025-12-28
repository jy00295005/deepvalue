# DeepValue MVP1 Design Doc (OpenAI + 中文日报)

## 1. MVP1 范围与目标

### 目标
- 覆盖标的：
  - Mag7：AAPL、MSFT、AMZN、NVDA、META、TSLA、GOOGL、GOOG
  - 大盘代理：QQQ
  - 重点监控列表：config 指定（用于详细 S/R 展示）
- 每日收盘后（EOD）自动生成：
  - 每票 DeepValueScore（0-100，带 5-10 日平滑）
  - 每票 S1/S2/S3、R1/R2/R3（确定性 levels）
  - 距离关键位的 $/%（确定性）
  - QQQ Market Regime + multiplier（确定性）
  - 最终策略（LLM 参与，但必须结构化+校验+可回退）
  - 中文日报 Markdown（LLM 参与，但必须可回退）

### 非目标（MVP1 不做）
- 盘中 last_price 距离刷新与提醒
- 新闻抓取/财报日历/新闻分拣
- 自动下单
- 回测/验证（放到 MVP2）
- Web UI/仪表盘（先用 Markdown + SQLite）

## 2. 总体流水线（Daily EOD）

1) Ingest：
- 拉取日线 OHLCV（>=6 年，最好 10 年）
- Stooq 主，yfinance 备（缺失/异常触发 fallback）
- 落库：prices_raw、prices_daily

2) Compute（确定性）：
- features_daily：pct_rank_5y、drawdown_3y、trend_hint、deepvalue_score_raw、deepvalue_score_smooth
- levels_daily：swing + 聚类 -> S1/S2/S3、R1/R2/R3
- market_state_daily：QQQ -> regime + multiplier
- baseline recommendations（确定性最小建议）

3) LLM（可控）：
- Strategy Narrator：生成最终策略 JSON
- Validator：严格校验（失败 -> 回退 baseline）
- Report Editor：生成中文日报 Markdown（失败 -> 回退模板日报）

4) Persist + Archive：
- recommendations_daily、reports、llm_cache、runs
- 产物可复盘：同日可幂等重跑

## 3. 数据与存储（SQLite）

核心表（MVP1 必须）：
- runs、prices_raw、prices_daily
- features_daily、levels_daily、market_state_daily
- recommendations_daily、reports
- llm_cache（建议 MVP1 就上）

价格口径：
- price_for_valuation = adj_close if not null else close
- features/levels/regime 的所有计算必须使用一致口径

## 4. Config（MVP1 最小集）

- universe_symbols：Mag7 + QQQ
- watchlist_symbols：可选
- history_min_years：6（建议 10）
- pct_rank_window_years：5
- drawdown_window_years：3
- score_smooth_days：7
- trend_sma_days：200

Levels：
- swing_window_k：例如 7
- cluster_tol_pct：例如 0.01
- max_levels：3

策略预算（固定 A）：
- budget_per_symbol_usd：每票预算基数
- ladder_default_weights_pct：S1=15、S2=25、S3=35
- reserve_pct=25（永远保留）

LLM（OpenAI）：
- provider=openai
- model/temperature/max_tokens
- schema_version、prompt_version（进入 cache_key）

## 5. LLM 子系统（MVP1 两角色）

### 5.1 Strategy Narrator（输出最终策略 JSON）
- 输入：确定性聚合 JSON（含 score/levels/距离/budget/默认份额/大盘状态）
- 输出：每票 action + 分档权重 + reserve + reasons + confidence
- 约束：不得输出新价位；不得输出未知 symbol；不得突破 validator 规则

### 5.2 Report Editor（输出中文 Markdown）
- 输入：market summary + ranking table + strategy json（已验证）
- 输出：content_md
- 建议：表格由确定性模板渲染，LLM 只写摘要/执行要点

## 6. Validator（MVP1 必须）

Strategy 硬校验：
- symbol 必须在 universe
- action 必须在枚举内
- ladder_weights_pct：S1/S2/S3 整数 0..100
- S1+S2+S3 <= 75
- reserve_pct >= 25
- S1+S2+S3+reserve_pct == 100
- 可选：S1 <= S2 <= S3

失败处理：
- 不通过：回退 baseline（15/25/35 + reserve 25 + baseline action）

## 7. 验收标准（DoD）
- 连续运行 5 个交易日无人工干预
- LLM 失败可自动回退且日报仍产出
- 同日可幂等重跑（主键不冲突、产物可追溯）
