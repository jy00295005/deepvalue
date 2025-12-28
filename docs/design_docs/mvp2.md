# DeepValue MVP2 Design Doc

## 1. MVP2 定位
在 MVP1（稳定日报 + 可控 LLM 策略）基础上，把系统升级为：
- 可验证（4 周回测/验证）
- 可提醒（盘中距离刷新 + 冷却提醒）
- 可扩展（新闻/财报/更多风控与观测）

## 2. MVP2 必须实现（核心）

### 2.1 4 周验证 / 回测（Deterministic）
目的：
- 用统一口径评估“分层吸筹”在最近窗口内的执行结果与对照组差异

成交价口径（固定）：
- 信号评估日：D（用 D 的 close/levels/距离判定触发）
- 成交执行日：D+1
- 成交价格：next_open(D+1)（使用 prices_daily.open）

触发逻辑（MVP2）：
- 距离 S1/S2/S3 < buffer 触发对应档位
- 冷却期 cooldown_days
- 资金约束：monthly cap / daily cap / per-symbol cap / cash buffer

落库：
- backtest_runs
- backtest_trades
- backtest_summary

对照组：
- 等权每日买入（同样 next_open 成交）

输出：
- 每票：投入、买入次数、均价
- 组合：总投入、分布
- 可选：LLM 写“解释段落”（数值必须来自回测输出）

### 2.2 盘中距离刷新与提醒（Intraday Distance-only）
目标：
- 不改变长期判断，只更新“离关键位还差多少”并触发提醒

数据：
- prices_intraday：last_price（15-60 分钟或接近触发带才查）

计算：
- 用 intraday last_price 计算到 levels_daily 的距离

提醒：
- 距离某档 S1/S2/S3 < intraday_buffer
- 冷却期：同一标的提醒不重复轰炸

强约束：
- Intraday 模式不得写 features_daily / levels_daily / market_state_daily（只写 intraday 和 alerts）

### 2.3 数据质量与可观测增强
- quality gate：缺失天数、极端波动复核、fallback 比例阈值告警
- 分 stage 记录 run 状态（ingest/features/levels/llm/report/backtest）

## 3. MVP2 可选增强（按优先级）
- 新闻/事件接入 + News Triage LLM（最小字段：timestamp/symbol/title/summary/source/url）
- 财报日历（财报前护栏）
- ATR% buffer / 波动率自适应

## 4. 验收标准（DoD）
- 回测：同窗口同配置重复运行输出一致，交易记录可复盘
- 盘中：不影响 EOD 产出且冷却期生效
- 观测：可定位数据异常来源（stooq vs yfinance）
