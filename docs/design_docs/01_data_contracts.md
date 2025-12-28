# Data Contracts (SQLite)

## Data layering
- Raw：按来源落库，便于追溯
- Clean：统一口径的日线序列（deterministic 模块只读这里）
- Snapshot：features/levels/market_state/reco/report 每日快照

## Canonical price policy
- price_for_valuation = adj_close if not null else close
- 统一口径用于：features、levels、regime

## Required tables (MVP)
- symbols
- runs
- prices_raw
- prices_daily
- features_daily
- levels_daily
- market_state_daily
- recommendations_daily
- reports
- llm_cache（MVP1 建议）

## Key columns (prices_daily)
- symbol, date (YYYY-MM-DD)
- open, high, low, close, volume
- adj_close (nullable)
- primary_source (stooq|yfinance)
- quality_flags (json string)

## Snapshot tables
- features_daily：分位、回撤、趋势提示、score_raw/score_smooth、price_used/is_adjusted
- levels_daily：s1/s2/s3/r1/r2/r3 + meta/flags
- market_state_daily：regime + multiplier + inputs json
- recommendations_daily：action + plan json + llm_used
- reports：daily/weekly markdown

## Quality flags (minimum)
- missing_fields
- extreme_move
- split_suspected
- fallback_used
- is_adjusted
