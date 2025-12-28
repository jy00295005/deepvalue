# Data Ingestion (Stooq primary, yfinance fallback)

## Cadence
- Daily EOD：更新日线 OHLCV
- Intraday（MVP2+）：last_price 距离刷新

## Source priority
- Primary：Stooq
- Fallback：yfinance

## Row-level selection
对同一 (symbol,date) 选择“整行来源”，避免字段拼接。

选择顺序：
1) Stooq 存在且通过校验 -> 用 Stooq
2) 否则用 yfinance（若通过校验）
3) 否则标记数据缺失

## Minimum quality checks
- close/volume 为空或 <=0 -> fail
- high < low -> fail
- 极端波动：abs(ret_1d) > 25% -> 标记 + 触发 fallback 复核

## Adjusted price
- 尽可能落库 adj_close
- 估值/结构计算优先用 adj_close
