# Scheduler / Runner (MVP)

## Daily EOD pipeline
- ingest (stooq->yfinance fallback)
- clean upsert prices_daily
- compute features
- compute levels
- compute market_state (QQQ)
- baseline recommendation
- llm strategy -> validate -> final recommendation
- report -> store

## Idempotence
- runs 记录 run_id + asof_date + mode + status
- 各表按 (symbol,date) 或 (date) 做 upsert

## Failure policy
- LLM 失败：回退 baseline，run 仍可 success（并记录 llm_used=0/validation_status）
- 数据缺失：对缺失 symbol 标记并跳过，不阻断全局（MVP）
