# Config Spec (MVP)

## Universe
- mag7_symbols: [AAPL, MSFT, AMZN, NVDA, META, TSLA, GOOGL, GOOG]
- market_proxy_symbol: QQQ
- watchlist_symbols: []

## Windows
- history_min_years: 6
- pct_rank_window_years: 5
- drawdown_window_years: 3
- score_smooth_days: 7
- trend_sma_days: 200

## Levels
- swing_window_k: 7
- cluster_tol_pct: 0.01
- max_levels: 3

## Policy / Budget
- budget_per_symbol_usd: 500
- ladder_default_weights_pct:
  - S1: 15
  - S2: 25
  - S3: 35
- reserve_pct: 25
- buffer_pct: 0.01
- cooldown_days: 5

## Market regime
- multipliers:
  - risk_on: 1.0
  - neutral: 0.9
  - risk_off: 0.7

## LLM (OpenAI)
- model: gpt-4o-mini
- temperature: 0.3
- max_output_tokens: 1200
- schema_version: v1
- prompt_version: v1
- cache_enabled: true
