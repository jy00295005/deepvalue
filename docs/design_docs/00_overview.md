# DeepValue - Overview

## Goals
- 监控：Mag7 +（可选）QQQ
- 输出长期“相对便宜”信号：DeepValueScore（0-100，平滑）
- 输出长期关键价位：S1/S2/S3（吸筹阶梯），R1/R2/R3（避免追高）
- 输出：收盘后中文日报；周末周报（MVP2+）

## Non-goals
- 不做日内择时/高频
- 默认不自动下单
- LLM 不负责数值计算与行情事实推断

## Invariants
- 所有关键数值（分数、分位数、回撤、levels、regime、距离、回测）必须由确定性代码生成
- LLM 输出必须结构化（JSON）并通过校验；失败必须回退 baseline
- 任意输出可追溯（runs + snapshots + llm_cache）

## Run modes
- Daily EOD：更新日线→算特征/分数→算 levels→算大盘→策略→日报
- Weekly（MVP2+）：汇总统计→周报
- Intraday（MVP2+）：仅更新 last_price 与距离/提醒，不改 score/levels
