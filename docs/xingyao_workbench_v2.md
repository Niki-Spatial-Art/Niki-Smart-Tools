# 星耀工作台模块清单 v2

> **更新于 2026-06-18**
> 
> v1 中规划的"星耀优先"战略已进入实质落地阶段。
> SDK 安装完成、环境变量配置完成、全接口测试通过。
> 详细连接状态见 [登录配置](xingyao_login_setup.md)，架构设计见 [MCP-Agent 三层架构](xingyao_mcp_agent_architecture.md)。
> 梅森交易知识库与持仓雷达融合见 [梅森 + 星耀综合体](mason_xingyao_integration.md)。

## 战略状态更新

| 里程碑 | 状态 | 日期 |
|--------|------|------|
| 星耀 SDK 安装 | ✅ 完成 | 2026-06-18 |
| 环境变量配置 | ✅ 完成 | 2026-06-18 |
| 登录测试 | ✅ 通过 | 2026-06-18 |
| 基础数据（日历/代码表） | ✅ 正常 | 2026-06-18 |
| 历史K线 | ✅ 正常 | 2026-06-18 |
| 财务报表 | ✅ 正常 | 2026-06-18 |
| 实时快照 | ⚠️ 接口可调用，需验证延迟 | - |
| 独立连接器 `connectors/xingyao.py` | ✅ 完成 | 2026-06-18 |
| MCP Server 封装 `tools/xingyao_mcp_server.py` | ✅ 完成 | 2026-06-18 |
| MCP-Agent 三层架构文档 | ✅ 完成 | 2026-06-18 |
| 梅森 + 星耀持仓雷达 | ✅ 完成 | 2026-06-19 |
| monitor.py 星耀函数 | ✅ 已有 20+ 函数 | - |
| 星耀工作台 v2 HTML 原型 | ✅ 已有 | - |
| FFD MCP 启用 | ⏳ 待启用 | - |
| 两融/龙虎榜 | ⏳ Phase 2 | - |
| 金融算子 | ⏳ 待探针 | - |

## 数据源路由（已更新）

```text
优先级 1: 星耀 AmazingData (主源 ✅)
   ├── 实时行情 → 快照 (待验证延迟)
   ├── 历史 K 线 → 完全可用
   ├── 财务报表 → 完全可用 (利润表/资产负债表/现金流)
   └── 基础数据 → 完全可用 (日历/代码表/复权因子)

优先级 2: 东方财富 (候补)
   ├── 全市场扫描
   └── ETF/A 股雷达

优先级 3: FFD MCP (待启用 ⏳)
   ├── 资金流向
   ├── 公告/研报
   └── 宏观数据

优先级 4: 腾讯/新浪/Yahoo (应急兜底)
```

## 新增能力

### 1. 独立连接器 (`connectors/xingyao.py`)

独立于 monitor.py 的可复用模块，提供：

- `login()` — 幂等登录，23 小时会话复用
- `get_calendar()` / `get_stock_list()` / `get_etf_list()` — 基础数据
- `get_kline()` / `get_snapshot()` — 行情数据
- `get_income()` / `get_balance()` / `get_cashflow()` — 财务数据
- `diagnostics()` — 一键诊断
- `is_configured()` / `is_enabled()` — 状态检查

### 2. MCP Server (`tools/xingyao_mcp_server.py`)

将星耀 SDK 封装为 8 个 MCP 工具，可在 AI Agent 中直接调用：

| MCP 工具 | 对应 SDK 功能 |
|----------|-------------|
| `xingyao_health` | 连接健康检查 |
| `xingyao_calendar` | 交易日历 |
| `xingyao_kline` | 历史 K 线 |
| `xingyao_snapshot` | 实时快照 |
| `xingyao_income` | 利润表 |
| `xingyao_balance` | 资产负债表 |
| `xingyao_search_stocks` | 代码搜索 |
| `xingyao_diagnostics` | 完整诊断 |

### 3. 梅森 + 星耀持仓雷达 (`tools/portfolio_radar_engine.py`)

持仓雷达现在会调用 `tools/mason_signal_engine.py` 输出梅森动作卡：

- 主线/支线：识别科技、光通信、半导体、小金属、港股、金融等风险桶
- 均线引力：根据价格与 MA20 的乖离率判断是否追高
- 双跌买点：用近 5 日回踩结构做低吸条件提示
- 同方向风险：识别 `515050` + `600487` 这类账户内重复暴露
- 账户纪律：按浮亏线输出减仓/清仓提示

### 4. 三层架构文档

详见 [MCP-Agent 三层架构设计](xingyao_mcp_agent_architecture.md)：

- **MCP 工具层**：星耀 SDK + FFD MCP 提供可调用数据接口
- **Skill 流程层**：ad-api / 复盘 / 选股 / ETF 诊断等流程模板
- **Agent 调度层**：WorkBuddy + monitor.py 负责任务编排

## 下一步优先级

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | FFD MCP 启用 | 补齐资金流/公告/研报 |
| P0 | 实时快照延迟验证 | 确认盘中数据新鲜度 |
| P1 | 星耀 MCP Server 实测 | 在 WorkBuddy 中运行 MCP 模式 |
| P1 | ETF 持仓诊断脚本 | 基于星耀财务数据 |
| P2 | 复盘/选股 Skill 封装 | 流程模板化 |
| P2 | 两融/龙虎榜探针 | Phase 2 数据层 |
