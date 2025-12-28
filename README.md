# DeepValue

> **3-5 年长期价值投资系统**：低价吸筹、分批建仓、长线持有

## 📈 回测结果 (2025年11-12月)

基于 $10,000 本金的两个月实测表现：

| Stock | Weight % | Unrealized % | Contribution |
|-------|----------|--------------|--------------|
| NVDA  | 24       | +5.12        | +$123        |
| TSLA  | 19       | +12.43       | +$236        |
| QQQ   | 17       | +3.35        | +$57         |
| META  | 14.5     | +8.79        | +$128        |
| MSFT  | 14.5     | -1.31        | -$19         |
| AMZN  | 6        | +2.75        | +$17         |
| AAPL  | 5        | +1.50        | +$8          |
| **Total** | **100** | **+6.82%** | **+$682**    |

> 📊 策略采用 S1/S2/S3 分层建仓，仓位分配：S1=20%, S2=30%, S3=40%, Reserve=10%

---

## 🎯 项目定位

**DeepValue 不是短线交易工具，而是为长期投资者设计的筹码积累系统。**

本系统专注于 MAG7（AAPL, MSFT, AMZN, NVDA, META, TSLA, GOOGL, GOOG）+ QQQ 的**长期价值评估**，帮助投资者：

- 🎯 **识别低估机会**：通过 DeepValue Score 找到相对便宜的买入时机
- 📊 **分层吸筹**：在 S1/S2/S3 支撑位分批建仓，避免一次性打光子弹
- 🛡️ **风险控制**：强制保留 25%+ 现金储备，应对进一步下跌
- ⏳ **长期持有**：目标持有周期 3-5 年，赚取企业成长的钱

### 核心理念

> "在别人恐慌时贪婪，在别人贪婪时恐惧。" —— 巴菲特

DeepValue 通过确定性算法 + 外部信号融合 + LLM 策略增强，帮你在市场波动中**系统化地低价攒筹码**，而不是追涨杀跌。

### 核心特性

- ✅ **确定性计算**：所有数值（分数、分位数、levels、距离）由规则生成，可追溯
- 🌐 **外部信号融合**：集成 Perplexity 技术分析作为独立决策源
- 🤖 **LLM 增强**：OpenAI 批量生成策略，严格校验，失败自动回退 baseline
- 📊 **完整 Pipeline**：数据采集 → 特征 → Levels → PP 融合 → 市场状态 → 策略 → 报告
- 🔒 **风控护栏**：强制 reserve ≥ 25%，accumulate 需 score ≥ 阈值

---

## 📐 系统架构流程图

<details>
<summary><b>点击展开完整流程图</b></summary>

### Stage 1️⃣ 数据采集 (Ingestion)

从外部数据源拉取历史价格数据（OHLCV），合并多源数据并清洗，写入数据库。

- **数据源**：Stooq (主) + yfinance (备)
- **输出表**：`prices_raw`, `prices_daily`
- **时间范围**：过去 6 年
- **覆盖范围**：MAG7 + QQQ

```
prices_daily: symbol, date, open, high, low, close, volume, adj_close, primary_source, quality_flags
```

---

### Stage 2️⃣ 特征计算 (Features)

基于价格历史计算技术指标、波动率、趋势强度等特征，生成 DeepValue Score。

- **技术指标**：SMA (20/50/200日)、RSI、MACD、布林带、ATR
- **DeepValue Score**：综合多因子打分（价格相对位置 + 趋势强度 + 波动率调整）
- **百分位排名**：`pct_rank_5y` - 当前 Score 在过去 5 年的历史分位数

```
features_daily: symbol, date, deepvalue_score_smooth, pct_rank_5y, rsi, macd, ...
```

**计算公式**：
- `pct_rank_5y`：0..1 (越低越便宜)
- `drawdown_3y`：0..1 (越高回撤越深)
- `deepvalue_score_raw`：加权得分 → 7 日平滑 → `deepvalue_score_smooth`

---

### Stage 3️⃣ 支撑/阻力位计算 (Levels)

基于 Swing High/Low 和均线，计算内部结构支撑位 S1/S2/S3 和阻力位 R1/R2/R3。

- **候选来源**：
  - `swing_5y` / `swing_1y` (历史低点)
  - `sma20` / `sma50` / `sma200`
  - 聚类去重、按强度排序
- **选择规则**：
  - **S1**：最近且强度最高
  - **S2**：更深、避免与 S1 太近
  - **S3**：长期防守位
- **元数据**：`s_meta` (JSON) 记录候选列表、选中原因、强度评分

```
levels_daily: symbol, date, s1, s2, s3, r1, r2, r3, s_meta, r_meta
```

---

### Stage 3.5️⃣ 🌐 Perplexity 融合 (PP Fusion)

**独立外部信号源**：读取手动保存的 Perplexity 外部支撑位快照，按融合规则调整 S1/S2（S3 不动）。

#### 🔑 关键设计

- **数据源**：本地 JSON 文件 `data/external/perplexity_supports/pp_supports_YYYY-MM-DD.json`
- **独立性**：Perplexity **不接收**历史价格数据，只基于公开技术分析/研报
- **手动快照**：每天手动保存（避免 API 成本 + 保证可复现）

#### 融合策略

| Level | 策略 | 说明 |
|-------|------|------|
| **S1** | Soft-blend | 加权平均 (max weight 0.6) + clamp 到合理范围 |
| **S2** | 条件替换 | 仅当内部 S2 弱时（strength < 1.5）才受 PP 影响 |
| **S3** | 不受影响 | 保持内部结构支撑，不被外部信号干扰 |

#### 权重控制

- **PP 最大权重**：0.6
- **置信度阈值**：0.4
- **derived_level**：confidence ≤ 0.40

#### 持久化

融合结果写回 `levels_daily.s1/s2` + `s_meta.pp_fusion`，报告会显示：
- **PP 状态**：used(0.78) / ignored(0.00)
- **PP 区间**：260.00-265.00
- **S1/S2 来源**：pp_fused / struct_5y

```sql
UPDATE levels_daily SET 
  s1 = fused_s1, 
  s2 = fused_s2,
  s_meta = json_set(s_meta, '$.pp_fusion', fusion_meta)
WHERE symbol=? AND date=?
```

---

### Stage 4️⃣ 市场状态 (Market State)

基于 QQQ 的技术指标判断市场风险偏好（risk_on / risk_off），调整仓位乘数。

- **判断依据**：
  - QQQ 相对 SMA50/200
  - RSI 过热/超卖
  - 波动率 (ATR)
- **输出**：
  - `regime`: risk_on / neutral / risk_off
  - `multiplier`: 0.5x ~ 1.5x (影响后续仓位分配)

```
market_state_daily: date, regime, multiplier, qqq_price, qqq_sma50, ...
```

---

### Stage 5️⃣ 基线策略 (Baseline Policy)

基于确定性规则生成初始推荐：action (hold/pause/accumulate) + 梯度买入权重。

- **决策规则**：
  - Score ≥ 阈值 → accumulate
  - Score 中等 → hold
  - Score 低 → pause_shallow
- **梯度权重**：
  - S1: 10-15%
  - S2: 15-25%
  - S3: 25-35%
  - reserve: 25-65%
- **市场调整**：根据 `market_state.multiplier` 动态调整 reserve 比例

```
recommendations_daily: symbol, date, action, plan_json, explain_json, llm_used=0
```

---

### Stage 6️⃣ LLM 策略增强 (Strategy Enhancement)

对 MAG7 批量调用 OpenAI，基于融合后的 levels + 市场状态微调策略（保留 baseline 作为 fallback）。

#### 输入上下文

- 融合后的 S1/S2/S3 (来自 Stage 3.5)
- DeepValue Score + Rank
- Market regime + multiplier
- Baseline action + weights

#### LLM 任务

**批量生成**（一次调用多只）：
- 微调 `ladder_weights_pct`
- 调整 `reserve_pct`
- 生成 `explain` (可解释性)

#### 校验回退

逐条验证 LLM 输出：
- 权重和 = 100%
- reserve ≥ 25%
- 不合规 → `baseline_fallback`

#### 💡 批量优化

原本逐只调用 LLM（9 次），现在改为**批量生成**（1 次），大幅降低成本与耗时。同时保留逐只校验，确保每条策略都符合规则。

```python
# 更新 recommendations_daily
UPDATE recommendations_daily SET 
  plan_json = llm_plan,
  explain_json = llm_explain,
  llm_used = 1
WHERE symbol=? AND date=?
```

---

### Stage 7️⃣ 报告生成 (Reporting)

汇总所有计算结果，生成 Markdown 格式的每日报告，展示排名、策略、PP 融合状态。

#### 报告内容

- 市场概览 (regime + top stocks)
- DeepValue 排名表
- 个股详情 (S1/S2/S3 + action + weights)
- **PP 融合状态/置信度/区间**

#### 新增列

| 列名 | 示例 | 说明 |
|------|------|------|
| **PP** | used(0.78) | PP 使用状态 + 置信度 |
| **PP Band** | 260.00-265.00 | PP 支撑区间 |
| **S1 Src** | pp_fused | S1 来源（pp_fused / struct_5y） |
| **S2 Src** | struct_3y | S2 来源 |

#### 存储

```
reports 表 (upsert): report_id, date, type, content_md, meta_json
```

#### 查看报告

```bash
python -m src.reporting.show_report
```

</details>

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/yourusername/DeepValue.git
cd DeepValue

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 添加 OPENAI_API_KEY
```

### 2. 初始化数据库

```bash
python -c "from src.data.store import DataStore; DataStore().init_db()"
```

### 3. 运行完整 Pipeline

```bash
# 执行每日 EOD 流程（数据采集 → 计算 → 报告）
python -m src.scheduler.runner
```

### 4. 查看报告

```bash
# 查看最新日报
python -m src.reporting.show_report
```

---

## 📂 项目结构

```
DeepValue/
├── data/
│   ├── deepvalue.db              # SQLite 数据库
│   └── external/
│       └── perplexity_supports/  # PP 手动快照 JSON
├── docs/
│   ├── design_docs/              # 设计文档
│   └── deepvalue_logic_flow.html # 交互式流程图
├── src/
│   ├── config/
│   │   └── settings.py           # 全局配置
│   ├── data/
│   │   ├── store.py              # 数据库模型
│   │   └── ingestion.py          # 数据采集
│   ├── compute/
│   │   ├── features.py           # 特征计算
│   │   ├── levels.py             # Levels + PP Fusion
│   │   ├── market_state.py       # 市场状态
│   │   └── policy.py             # 基线策略
│   ├── llm/
│   │   ├── client.py             # OpenAI 客户端
│   │   ├── service.py            # LLM 服务（批量生成）
│   │   ├── validator.py          # 策略校验器
│   │   └── perplexity_client.py  # PP 客户端（手动快照）
│   ├── reporting/
│   │   ├── daily_report.py       # 报告生成
│   │   └── show_report.py        # 报告查看
│   └── scheduler/
│       └── runner.py             # 主流程编排
└── requirements.txt
```

---

## 🔧 配置说明

### 核心参数 (`src/config/settings.py`)

```python
# Universe
MAG7_SYMBOLS = ["AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOGL", "GOOG"]
MARKET_PROXY_SYMBOL = "QQQ"

# 特征窗口
PCT_RANK_WINDOW_YEARS = 5
DRAWDOWN_WINDOW_YEARS = 3
SCORE_SMOOTH_DAYS = 7

# Levels
SWING_WINDOW_K = 7
CLUSTER_TOL_PCT = 0.01

# 策略预算
BUDGET_PER_SYMBOL_USD = 500
LADDER_DEFAULT_WEIGHTS_PCT = {"S1": 15, "S2": 25, "S3": 35}
RESERVE_PCT = 25
```

---

## 🌐 Perplexity 手动快照

### 文件格式

`data/external/perplexity_supports/pp_supports_YYYY-MM-DD.json`

```json
{
  "date": "2025-12-28",
  "symbols": {
    "AAPL": {
      "approx_price": 172.50,
      "supports": [
        {
          "kind": "range",
          "low": 165.0,
          "high": 170.0,
          "horizon": "short_term",
          "strength": 3,
          "confidence": 0.78,
          "evidence_type": "technical_level",
          "note": "Support from TradingView analysis..."
        }
      ]
    }
  }
}
```

### 生成快照

使用 Perplexity API 或手动整理技术分析数据，保存为上述格式。系统会在 Stage 3.5 自动读取并融合。

---

## 📊 数据表结构

### 核心表

| 表名 | 说明 |
|------|------|
| `prices_daily` | 清洗后的日线价格 |
| `features_daily` | DeepValue Score + 技术指标 |
| `levels_daily` | S1/S2/S3 + R1/R2/R3 + PP 融合结果 |
| `market_state_daily` | QQQ 市场状态 |
| `recommendations_daily` | 策略推荐（baseline + LLM） |
| `reports` | 每日报告 Markdown |
| `llm_cache` | LLM 调用缓存 |

---

## 🎯 设计原则

### 1. 长期主义：3-5 年持有周期

**DeepValue 的核心目标是帮助投资者在 3-5 年周期内积累优质筹码，而非短期交易。**

- 📉 **低价吸筹**：在市场回调时系统化建仓，不追涨
- 🪜 **分层买入**：S1/S2/S3 三档支撑位分批进场，摊低成本
- 💰 **保留弹药**：强制 25%+ 现金储备，应对更深回调
- ⏳ **耐心持有**：目标持有 3-5 年，赚企业成长的钱，而非波段差价

### 2. 确定性优先

所有关键数值（分数、分位数、levels、距离）必须由确定性代码生成，可追溯、可复现。

### 3. LLM 作为增强层

- LLM 不负责数值计算与行情事实推断
- LLM 输出必须结构化（JSON）并通过校验
- 失败必须回退 baseline

### 4. 外部信号独立性

Perplexity 作为独立决策源，不接收历史价格数据，只基于公开技术分析/研报，避免循环依赖。

### 5. 风控护栏

- 强制 `reserve_pct ≥ 25%`（永远保留弹药）
- `accumulate` 需 `score ≥ ACCUMULATE_SCORE_MIN`（避免盲目抄底）
- 权重必须单调：S1 ≤ S2 ≤ S3（越跌越买）

---

## 📈 可视化

### 交互式流程图

在浏览器中打开 `docs/deepvalue_logic_flow.html`，查看完整的交互式流程图，包含：
- 7 个核心阶段
- 每个阶段的输入/输出/规则
- PP Fusion 特别高亮
- 鼠标悬停效果

```bash
open docs/deepvalue_logic_flow.html
```

---

## 🛠️ 开发指南

### 运行单个模块

```bash
# 数据采集
python -m src.data.ingestion

# 特征计算
python -m src.compute.features

# Levels 计算
python -m src.compute.levels

# 市场状态
python -m src.compute.market_state

# 基线策略
python -m src.compute.policy
```

### 验证数据

```bash
# 验证采集结果
python -m src.data.verify_ingestion

# 验证计算结果
python -m src.compute.verify_compute
```

---

## 📝 设计文档

详细设计文档位于 `docs/design_docs/`：

- `00_overview.md` - 项目概览
- `01_data_contracts.md` - 数据契约
- `03_features_deepvalue_score.md` - 特征计算
- `04_levels_engine.md` - Levels 引擎
- `06_llm_subsystem.md` - LLM 子系统
- `mvp1.md` - MVP1 完整设计
- `mvp2.md` - MVP2 规划（回测/盘中提醒）

---

## ⚠️ 免责声明

本系统仅供学习和研究使用，不构成任何投资建议。

**重要提示**：
- ⏳ **长期投资**：本系统设计用于 3-5 年长期持有，不适合短线交易
- 📉 **波动承受**：长期投资需要承受短期波动，可能面临账面浮亏
- 💰 **资金管理**：只用闲钱投资，不要借钱或使用短期需要的资金
- 🎯 **自主决策**：系统提供参考，最终决策由投资者自行负责

使用者需自行评估风险，并对投资决策负责。

---

## 📄 License

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**Built with ❤️ by DeepValue Team**
