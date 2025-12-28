# Reporting (MVP1)

## Daily report (Chinese)
Minimum sections:
- Market：QQQ regime + multiplier
- Ranking：Mag7 排名表（score_smooth、分位、回撤、是否复权）
- Watchlist：S/R + 距离 + 最终策略（含 reserve）
- 执行要点：LLM 摘要（失败回退到模板）

## Rendering strategy
- 表格与数值：确定性模板渲染
- 摘要/注意事项：LLM 生成（必须可回退）

## Storage
- reports 表：date/type/content_md/meta_json
