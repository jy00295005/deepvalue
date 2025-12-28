# Observability (MVP)

## Daily checks
- 缺失：close/volume 为空
- 异常：abs(ret_1d) > 阈值（默认 25%）
- fallback：使用 yfinance 比例

## Alerts (MVP)
- run failed
- fallback 比例过高
- 单票连续缺失 N 天

## Logging
- 记录 run_id/stage/symbol/message/meta_json
