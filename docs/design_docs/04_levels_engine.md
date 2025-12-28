# Levels Engine (Deterministic)

## Goal
- 生成 S1/S2/S3 + R1/R2/R3
- 下游（策略/LLM/报告）只能引用 levels_daily 的价位

## Canonical input
- 与 features 同一口径：adj_close 优先（缺失则 close）

## MVP algorithm
- swing high/low 检测（窗口 k）
- 价格聚类（容差 tol_pct）
- 根据强度与相对当前价的位置选择 3 个支撑与 3 个压力

## Output
- levels_daily: s1/s2/s3/r1/r2/r3 + meta json + quality flags

## Distance contract
- %dist = level/current - 1
- intraday（MVP2+）：只更新距离，不改 score/levels
