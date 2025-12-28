# DeepValue Daily Report - 2025-12-26

## 1. Market Overview
**Regime**: risk_on
**Multiplier**: 1.00x

市场状态：risk_on，风险乘数 1.0。今日 Top Rank 名单：META, MSFT, AMZN。

## 2. DeepValue Rankings
| Symbol | Score | Rank(5y) | Action | Reserve | Strategy | PP | PP Band | S1 Src | S2 Src | S3 Src | S1 Dist |
|---|---|---|---|---|---|---|---|---|---|---|---|
| META | 30 | 0.90 | hold | 25% | llm | used(0.56) | 580.00-600.00 | pp_fused | struct_1y | struct_5y | -7.3% |
| MSFT | 8 | 0.91 | hold | 30% | llm | used(0.78) | 482.00-482.00 | struct_5y | struct_5y | struct_5y | -2.9% |
| AMZN | 6 | 0.97 | hold | 30% | llm | missing_or_low_confidence(0.00) | - | struct_5y | struct_5y | - | -5.2% |
| NVDA | 5 | 0.99 | hold | 35% | llm | used(0.82) | 176.34-176.34 | pp_fused | struct_5y | struct_5y | -4.9% |
| AAPL | 2 | 0.98 | hold | 40% | llm | used(0.72) | 198.00-202.00 | pp_fused | pp_fused | struct_5y | -10.3% |
| GOOGL | 2 | 0.99 | pause_shallow | 45% | llm | missing_or_low_confidence(0.36) | - | sma50 | struct_5y | struct_5y | -6.5% |
| GOOG | 2 | 0.99 | pause_shallow | 45% | llm | missing_or_low_confidence(0.36) | - | sma50 | struct_5y | struct_5y | -6.7% |
| QQQ | 2 | 0.99 | hold | 25% | baseline | used(0.75) | 565.00-565.00 | pp_fused | struct_5y | struct_5y | -7.4% |
| TSLA | 1 | 0.99 | pause_shallow | 50% | llm | used(0.80) | 370.00-370.00 | pp_fused | pp_fused | struct_5y | -6.5% |

## 3. Execution Notes
- 按市场状态执行：risk_on。
- 遵循分批、保留充足 reserve 的纪律，避免一次性打光子弹。
- 仅基于确定性指标与已校验策略展示，不使用 LLM 自由发挥文案。

## 4. Watchlist Details

### META (30)
**Action**: hold
**Price**: 663.29
- **strategy_source**: llm
- **reserve_pct**: 25%
- **pp_status**: used(0.56)
- **pp_band**: 580.00-600.00
- **S1**: 614.61 (20%) [pp_fused]
- **S2**: 591.70 (25%) [struct_1y]
- **S3**: 484.61 (30%) [struct_5y]
**Reasons**:
- Rank(5y)=0.90，Score=30.1。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -7.3%。
- Action=hold；reserve=25%。

### MSFT (8)
**Action**: hold
**Price**: 487.71
- **strategy_source**: llm
- **reserve_pct**: 30%
- **pp_status**: used(0.78)
- **pp_band**: 482.00-482.00
- **S1**: 473.47 (20%) [struct_5y]
- **S2**: 450.18 (22%) [struct_5y]
- **S3**: 413.50 (28%) [struct_5y]
**Reasons**:
- Rank(5y)=0.91，Score=7.6。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -2.9%。
- Action=hold；reserve=30%。

### AMZN (6)
**Action**: hold
**Price**: 232.52
- **strategy_source**: llm
- **reserve_pct**: 30%
- **pp_status**: missing_or_low_confidence(0.00)
- **S1**: 220.52 (18%) [struct_5y]
- **S2**: 212.34 (22%) [struct_5y]
- **S3**: 166.51 (30%) [-]
**Reasons**:
- Rank(5y)=0.97，Score=5.8。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -5.2%。
- Action=hold；reserve=30%。

### NVDA (5)
**Action**: hold
**Price**: 190.53
- **strategy_source**: llm
- **reserve_pct**: 35%
- **pp_status**: used(0.82)
- **pp_band**: 176.34-176.34
- **S1**: 181.28 (15%) [pp_fused]
- **S2**: 177.00 (20%) [struct_5y]
- **S3**: 167.02 (30%) [struct_5y]
**Reasons**:
- Rank(5y)=0.99，Score=5.3。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -4.9%。
- Action=hold；reserve=35%。

### AAPL (2)
**Action**: hold
**Price**: 273.40
- **strategy_source**: llm
- **reserve_pct**: 40%
- **pp_status**: used(0.72)
- **pp_band**: 198.00-202.00
- **S1**: 245.27 (15%) [pp_fused]
- **S2**: 200.00 (20%) [pp_fused]
- **S3**: 226.36 (25%) [struct_5y]
**Reasons**:
- Rank(5y)=0.98，Score=2.2。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -10.3%。
- Action=hold；reserve=40%。

### GOOGL (2)
**Action**: pause_shallow
**Price**: 313.51
- **strategy_source**: llm
- **reserve_pct**: 45%
- **pp_status**: missing_or_low_confidence(0.36)
- **S1**: 293.02 (12%) [sma50]
- **S2**: 276.41 (18%) [struct_5y]
- **S3**: 236.57 (25%) [struct_5y]
**Reasons**:
- Rank(5y)=0.99，Score=2.0。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -6.5%。
- Action=pause_shallow；reserve=45%。

### GOOG (2)
**Action**: pause_shallow
**Price**: 314.96
- **strategy_source**: llm
- **reserve_pct**: 45%
- **pp_status**: missing_or_low_confidence(0.36)
- **S1**: 293.73 (12%) [sma50]
- **S2**: 276.98 (18%) [struct_5y]
- **S3**: 237.49 (25%) [struct_5y]
**Reasons**:
- Rank(5y)=0.99，Score=1.8。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -6.7%。
- Action=pause_shallow；reserve=45%。

### QQQ (2)
**Action**: hold
**Price**: 623.89
- **strategy_source**: baseline
- **reserve_pct**: 25%
- **pp_status**: used(0.75)
- **pp_band**: 565.00-565.00
- **S1**: 577.42 (15%) [pp_fused]
- **S2**: 563.28 (25%) [struct_5y]
- **S3**: 506.78 (35%) [struct_5y]
**Reasons**:
- Rank(5y)=0.99，Score=1.8。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -7.4%。
- Action=hold；reserve=25%。

### TSLA (1)
**Action**: pause_shallow
**Price**: 475.19
- **strategy_source**: llm
- **reserve_pct**: 50%
- **pp_status**: used(0.80)
- **pp_band**: 370.00-370.00
- **S1**: 444.14 (10%) [pp_fused]
- **S2**: 370.00 (15%) [pp_fused]
- **S3**: 391.09 (25%) [struct_5y]
**Reasons**:
- Rank(5y)=0.99，Score=0.7。
- 排名靠前但不代表便宜；低估/吸筹等措辞已禁用（score 未达阈值）。
- 距离 S1 约 -6.5%。
- Action=pause_shallow；reserve=50%。

## 5. Risk Warning
本报告基于确定性规则生成，仅作参考，不构成投资建议。请自行评估风险与合规要求。
