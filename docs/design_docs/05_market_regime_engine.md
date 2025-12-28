# Market Regime Engine (QQQ)

## Goal
- 给出大盘环境：regime + multiplier
- 仅作为“强度乘数/护栏”，不推翻个股长期便宜逻辑

## Input
- QQQ prices_daily（adj_close 优先）

## MVP rule
- SMA200 + slope 判断 risk_on/neutral/risk_off

## Output
- market_state_daily(date, regime, multiplier, inputs_json)
