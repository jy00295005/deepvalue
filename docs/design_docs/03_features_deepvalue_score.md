# Features & DeepValue Score (Deterministic)

## Inputs
- prices_daily (>= 6y)

## Canonical price
- price_for_valuation = adj_close if not null else close

## Features (MVP)
- pct_rank_5y: 0..1（越低越便宜）
- drawdown_3y: 0..1（越高回撤越深）
- trend_hint: 基于 SMA200 的提示（确定性）

## Score (0..100)
- deepvalue_score_raw: 由以上特征加权得到并裁剪到 [0,100]
- deepvalue_score_smooth: 5-10 日 SMA/EMA 平滑（默认 7 日）

## Output
- features_daily 每 symbol 每日一行：
  - price_used/is_adjusted
  - pct_rank_5y/drawdown_3y/trend_hint
  - score_raw/score_smooth
