# 星耀 MCP-Agent 三层架构设计

> 基于 2026-06-18 实际对接成果，梳理星耀数智在 WorkBuddy/Niki-Smart-Tools 生态中的三层架构。

## 架构总览

```
用户自然语言问题
       ↓
  Prompt / 任务约束
       ↓
  Agent 调度器 (WorkBuddy / monitor.py)
       ↓
  Skill 流程选择 (ad-api / 复盘 / 选股 / 因子分析)
       ↓
  MCP 工具调用 或 Python SDK 直调
       │
       ├── 星耀 AmazingData SDK (已打通 ✅)
       │     ├── 行情：K线、快照
       │     ├── 财务：利润表、资产负债表、现金流量表
       │     ├── 基础：交易日历、代码列表、复权因子
       │     ├── 股东：股东户数、股权质押
       │     ├── 资金：融资融券、龙虎榜 (Phase 2)
       │     └── 专题：期权、ETF、指数、行业
       │
       └── FFD MCP (已配置，待启用 ⏳)
             ├── 资金流 ffd_money_flow
             ├── 公告 ffd_announcements
             ├── 研报 ffd_research_search
             ├── 选股 ffd_screen_stocks
             └── 宏观 ffd_macro_data
       ↓
  权限、日志、风控
       ↓
  输出：图表、报告、提醒、动作卡
```

## 第一层：MCP 工具层（数据与功能接口）

### 星耀 AmazingData（Python SDK 模式）

**当前状态：✅ 已打通**

| 组件 | 状态 | 详情 |
|------|------|------|
| tgw 通信层 | ✅ 1.0.8.7 已安装 | 64MB wheel，处理 TCP 长连接 |
| AmazingData SDK | ✅ 1.1.6-cp313 已安装 | 完整数据接口 |
| 环境变量 | ✅ 已配置 | AD_USERNAME/PASSWORD/HOST/PORT 写入 Windows 用户级 |
| 登录 | ✅ 正常 | Token 获取正常 |
| 交易日历 | ✅ 8664 个 | 最新 2026-06-18 |
| A 股列表 | ✅ 5528 只 | 全量返回 |
| ETF 列表 | ✅ 1563 只 | 全量返回 |
| 历史 K 线 | ✅ 正常 | 日/周/月/分钟级 |
| 实时快照 | ⚠️ 需联调 | 快照接口可调用，需验证盘中延迟 |
| 财务数据 | ✅ 正常 | 利润表/资产负债表/现金流量表 |
| 本地缓存 | ⚠️ 权限 | D:\AmazingData_local_data\ 需沙箱授权 |

### FFD MCP （标准 MCP 协议，stdio 模式）

**当前状态：⏳ 已配置，待 WorkBuddy 连接器管理页启用**

配置文件：`~/.workbuddy/.mcp.json`
```
ffd → stdio MCP Server v0.6.17
  30+ 金融数据工具已注册
```

---

## 第二层：Skill 流程层（研究流程模板）

### 已安装 Skills

| Skill | 功能 | 数据源 |
|-------|------|--------|
| `ad-api` | 星耀金融数据 API 调用模板 | 星耀 SDK |
| `ad-factor-analysis` | 因子分析框架（IC/回归/分层/拥挤度） | 星耀 SDK |
| `ad-fundamental-analysis` | 90 个基本面指标（9 大类） | 星耀 SDK |
| `ad-technical-analysis` | 56 个技术指标（7 大类） | 星耀 SDK |
| `stock-analyzer` | 全球股票综合分析（东方财富） | 东方财富 |
| `ffd-finflow-data` | FFD 金融数据 API 指南 | FFD MCP |

### 待封装的流程 Skill

```
复盘 Skill = 拉行情 → 看资金 → 查公告 → 生成结论
选股 Skill = 行业池 → 财务指标 → 技术指标 → 资金过滤 → 输出列表
风险扫描 Skill = 持仓快照 → 止损校验 → 事件风险 → 仓位建议
ETF 诊断 Skill = 折溢价 → 成分股 → 资金流 → 行业轮动 → 评分
```

---

## 第三层：Agent 调度层

### WorkBuddy 作为调度器

- 理解自然语言 → 选择 Skill → 调用 MCP 工具 → 整理输出
- 对话上下文记忆，连续多步骤执行
- 文件系统读写，生成报告/图表

### monitor.py 作为本地调度器

- 定时任务触发（Windows 计划任务 / GitHub Actions）
- 数据源路由（星耀优先 → 东方财富候补 → 腾讯/新浪应急）
- 动作卡生成规则 + AI 摘要（通义千问）
- 纸面交易日志闭环

---

## 数据源路由规则（更新后）

```
优先级 1: 星耀 AmazingData (主源，已打通)
   ├── 实时行情 → 当前仍需东方财富补充快照延迟
   ├── 历史 K 线 → 完全可用
   ├── 财务报表 → 完全可用
   └── 基础数据 → 完全可用

优先级 2: 东方财富 (候补)
   ├── 全市场扫描
   └── ETF/A 股雷达

优先级 3: FFD MCP (待启用)
   ├── 资金流向（东方财富替代）
   ├── 公告/研报（独有优势）
   └── 宏观数据（独有优势）

优先级 4: 腾讯/新浪/Yahoo (应急兜底)
```

---

## 对接时间线

| 日期 | 里程碑 |
|------|--------|
| 2026-06-18 | 星耀 SDK 本地安装完成，全接口测试通过 |
| 2026-06-18 | 环境变量配置完成（Windows 用户级永久） |
| 2026-06-18 | `connectors/xingyao.py` 独立连接器模块创建 |
| 待定 | FFD MCP 启用 |
| 待定 | 星耀 SDK → MCP Server 封装 |
| 待定 | 复盘/选股/ETF 诊断 Skill 封装 |

---

## 与 Niki-Smart-Tools 工作台的集成

```
Niki-Smart-Tools/
├── connectors/
│   ├── xingyao.py          ← 新建：星耀独立连接器
│   ├── ifind_http.py
│   └── public_web_scraper.py
├── tools/
│   ├── xingyao_data_probe.py
│   └── xingyao_mcp_server.py  ← 计划：星耀 MCP Server 封装
├── docs/
│   ├── xingyao_login_setup.md    ← 已更新
│   ├── xingyao_workbench_v1.md
│   └── xingyao_mcp_agent_architecture.md  ← 新建
├── dashboards/
│   ├── dashboard.html       ← 星耀工作台 v2 原型
│   └── dashboard_v2.html
└── monitor.py               ← 核心调度器（含星耀全部函数）
```
