# LLM Subsystem (MVP1)

## Roles
- Strategy Narrator：输出策略 JSON
- Report Editor：输出中文日报 Markdown

## Hard constraints
- LLM 不做数值计算（score/levels/regime/距离/预算）
- LLM 不得输出新价位；引用价位必须来自 levels_daily
- 所有 LLM 输出必须通过 validator；失败必须回退 baseline

## Strategy output schema (concept)
- asof_date
- items[]:
  - symbol
  - action: accumulate|hold|pause_shallow
  - ladder_weights_pct: {S1,S2,S3}
  - reserve_pct
  - avoid_chasing
  - reasons (<=3)
  - confidence (0..1)

## Validator rules (minimum)
- symbol 属于 universe
- 权重为整数 0..100
- S1+S2+S3 <= 75
- reserve_pct >= 25
- S1+S2+S3+reserve_pct == 100

## Cache
- cache_key = hash(input_json + model + schema_version + prompt_version)
- llm_cache 落库 input/output/validation_status
