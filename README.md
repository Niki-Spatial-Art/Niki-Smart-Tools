# 基于 iFind 的 A股盘中交易决策工作台

[![ETF Strategy Monitor](https://github.com/Niki-Spatial-Art/Niki-Smart-Tools/actions/workflows/monitor.yml/badge.svg)](https://github.com/Niki-Spatial-Art/Niki-Smart-Tools/actions/workflows/monitor.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![No Auto Trading](https://img.shields.io/badge/no%20auto%20trading-human%20review%20required-orange)](#限制与免责声明)

这是一个面向个人 A股 / ETF 交易的本地决策工作台。它以 iFind 探针和本地回测为核心，把盘中行情、持仓风险、动作卡、纸面交易日志、盘后复盘和每日维护记录整理到一个可执行的流程里。

它更像一个「交易纪律副驾驶」，不是自动下单工具。每天盘前、盘中、盘后，它主要帮你回答：

- 今天先处理哪些旧仓？
- 哪些票只是观察，不能硬追？
- 如果要买，买点、止损、仓位是多少？
- 没买的票后面有没有错过，过滤条件要不要调整？
- 数据源是否新鲜，iFind / 东财 / 券商截图有没有互相打架？

本项目只做研究、提醒、复盘和纸面交易记录，不连接券商下单，不自动交易，也不承诺收益。所有真实买卖都必须由使用者自己确认和执行。

## 适合谁

- 想把冲动交易变成动作卡纪律的个人投资者。
- 想学习 A股 / ETF 量化流程、回测、风控和复盘的人。
- 想用 iFind、东方财富、券商截图和本地日志做一个小型个人研究台的人。
- 需要 GitHub Actions、Windows 定时任务、本地网页工作台三套方式互相兜底的人。

## 项目定位

一句话：

> 基于 iFind 的 A股盘中交易决策工作台：盘前计划、盘中动作卡、持仓风控、回测复盘和每日维护记录。

它关注的不是“自动替你买卖”，而是把交易前后的关键问题写清楚：

- 数据从哪里来，是否实时，是否缺字段。
- 信号为什么出现，是否经过回测覆盖。
- 仓位能买多少，止损亏多少，T+1 怎么处理。
- 旧仓先减压还是继续持有。
- 没买的票如何继续轮动回测和复盘。

## 对外展示亮点

如果要用一句话介绍给技术交流会或云厂商活动：

> 这是一个“少架构”的个人 A股盘中交易决策工作台：iFind 做高质量数据底座，通义千问做可选中文策略简报，本地工作台把盘中动作卡、回测反馈、纸面交易日志和每日维护记录放在一起。

适合演示的 5 个点：

- **少架构**：没有引入复杂服务链路，优先用本地文件、探针和一个浏览器工作台闭环。
- **数据透明**：每张卡都显示数据来源、更新时间、是否可执行，而不是只给一个买卖结论。
- **人工确认**：系统只生成动作卡和风险线，不连接券商、不自动下单。
- **可复盘**：没买的票也保留 no-trade 样本，用来校正过滤条件。
- **可降级**：没有 iFind 时仍能作为交易纪律模板使用，但高置信动作卡会降级。

## 核心功能

- **iFind 数据底座**：实时行情、基础数据、智能选股、历史行情、日内快照、公告查询的本地探针。
- **盘中动作卡**：把“做/不做、买多少、哪里止损、哪里止盈、下一次检查时间”写成可执行提醒。
- **行情与备份源**：东方财富、腾讯、新浪、Yahoo 兜底行情；星耀 / 玉衡期权基础数据探针。
- **雷达与观察池**：ETF 红黄绿状态、A股强势观察、AI 基建主题池、期权仿真。
- **风险纪律**：不追高、日内亏损软硬止损、T+1 提醒、单票仓位上限、QDII 溢价提醒、现金底线。
- **纸面交易日志**：先写计划，再补实际成交、退出价、PnL 和复盘。没买的票也保留样本，用于后续学习。
- **本地工作台**：用浏览器打开 `http://127.0.0.1:8501/` 查看持仓、雷达、iFind 状态、回测、日志和学习报告。
- **学习报告**：把回测、错误卡、明日实验卡、因子录入判断和数据缺口写成简洁学习报告，而不是只堆表格。
- **每日维护记录**：把每天系统改了什么、交易纪律学到什么、明天该怎么修，单独沉淀成维护页。
- **自动化**：GitHub Actions、Windows 任务计划、本地半小时动作卡巡检。

## 阿里云相关能力

已接入的阿里云能力是可选 AI 摘要层：

- **通义千问 / DashScope OpenAI-compatible Chat Completions**
- 使用文件：`ai_client.py`
- 默认 provider：`qwen`
- 默认模型：`qwen-plus`
- 默认环境变量：`DASHSCOPE_API_KEY`
- 默认端点：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 用途：生成中文策略简报、风险提醒和盘后总结

如果没有 `DASHSCOPE_API_KEY`，或设置 `AI_ENABLED=false`，项目会跳过 AI 简报，其它本地雷达、动作卡、维护记录仍可运行。

详见：[阿里云 API 使用说明](docs/alicloud_api_usage.md)。

## 工作流

```text
数据源
  -> 行情标准化
  -> ETF / A股 / 期权雷达
  -> 回测与风险闸门
  -> 动作卡
  -> 纸面交易日志
  -> 本地工作台 / 邮件 / GitHub Actions
  -> 人工确认与盘后复盘
```

## 快速开始

```powershell
git clone https://github.com/Niki-Spatial-Art/Niki-Smart-Tools.git
cd Niki-Smart-Tools
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

创建本地配置：

```powershell
Copy-Item .env.example .env
Copy-Item portfolio.example.json portfolio.local.json
notepad .env
notepad portfolio.local.json
```

`portfolio.local.json` 用来放真实资金、仓位、现金策略和风险限制，默认不提交到 GitHub。

## 常用命令

生成主雷达报告：

```powershell
python monitor.py
```

刷新 iFind 全量探针：

```powershell
python tools/ifind_http_probe.py --all
```

刷新 iFind 实时 20 标的样本：

```powershell
python tools/ifind_http_probe.py --quick20
```

导出动作卡到纸面交易日志：

```powershell
python tools/action_audit.py export-plan --report reports/latest.json --journal data/paper_trade_journal.csv
```

启动本地工作台：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard_local.ps1
```

然后打开：

```text
http://127.0.0.1:8501/
```

生成简洁学习报告：

```powershell
python tools/learning_intake.py --sources examples/learning_sources.json --output reports/learning_intake.md
```

本地全量刷新：

```powershell
python tools/full_system_rerun.py
```

## iFind 使用说明

iFind 是本项目的重要数据源，但页面会区分三种状态：

- **已接通**：这一项探针本轮确实跑过，并返回成功。
- **本轮未运行**：当前探针没有执行这一项，不代表接口坏了。
- **未接通**：执行了但失败，需要检查 token、权限、字段或接口状态。

常见探针包括：

- 实时行情：盘中价格、成交额、量比校验。
- 基础数据：排除不可交易、ST、估值和基础字段风险。
- 智能选股：作为候选池交叉验证，不直接触发买入。
- 历史行情：回测、相似形态胜率、止盈止损线。
- 日内快照：盘中动作卡和关键时间点复盘。
- 公告查询：买入前事件风险闸门。

## iFind 授权与隐私

公开仓库不会提供 iFind token。使用者都须配置自己的 iFind 账号和接口权限。

没有 iFind 的用户仍然可以把本项目当成 A股 / ETF 交易纪律工作台模板使用，但会降级：

- 公开行情源可以做基础观察。
- 纸面交易日志、动作卡模板、每日维护记录可以正常使用。
- iFind 实时行情、历史回测、公告风险闸门、智能选股会显示未配置或未接通。
- 没有 iFind 时，不应输出高置信买入动作卡，只能降级观察。

详见：[iFind 授权与隐私说明](docs/ifind_auth_and_privacy.md)。

## 借鉴的优秀案例

本项目参考了几个成熟开源/平台型项目的组织方式，但做了个人 A股场景的轻量化取舍：

- **OpenBB**：借鉴“金融数据平台给分析师、量化和 AI Agent 使用”的统一入口思路。
- **QuantConnect LEAN**：借鉴研究、回测、实盘框架分层清楚的工程组织方式。
- **Freqtrade**：借鉴 dry-run、回测、风险保护、WebUI 和配置边界。
- **MongoDB / AI Search 架构思路**：借鉴“更少架构”的理念，把交易记录、维护记录、动作卡先收敛到一个工作台，后续再考虑统一检索层。

详见：[优秀案例借鉴](docs/reference_cases.md)。

## GitHub Actions

手动运行：

```text
Actions -> ETF Strategy Monitor -> Run workflow
```

主要工作流：

- `monitor.yml`：交易时段雷达监控。
- `action-audit.yml`：动作卡审计与纸面计划。
- `learning-intake.yml`：学习资料摄取与报告。
- `ci.yml`：Python 编译检查和离线 demo。

需要配置的 GitHub Secrets：

```text
SENDER_EMAIL
SENDER_PASSWORD
RECIPIENT_EMAIL
```

可选：

```text
AI_ENABLED
AI_PROVIDER
DASHSCOPE_API_KEY
KIMI_API_KEY
DEEPSEEK_API_KEY
XINGYAO_ENABLED
XINGYAO_USER
XINGYAO_PASSWORD
XINGYAO_HOST
XINGYAO_PORT
XINGYAO_SDK_PATHS
```

## 目录结构

```text
.
|-- monitor.py                 # 主雷达与报告流程
|-- ai_client.py               # 可选 AI 摘要客户端
|-- emailer.py                 # 邮件发送
|-- portfolio.json             # 公开示例配置
|-- portfolio.example.json     # 本地配置模板
|-- portfolio.local.json       # 私有持仓配置，不提交
|-- digital_infra_watchlist.json
|-- tools/
|   |-- action_audit.py        # 动作卡导出、通知、汇总
|   |-- ifind_http_probe.py    # iFind 探针
|   |-- learning_intake.py     # 学习报告
|   `-- local_dashboard.py     # 本地网页工作台
|-- agents/                    # Agent 职责说明
|-- workflows/                 # 工作流文档和 demo
|-- connectors/                # 数据接口说明
|-- strategies/                # 策略与风控规则
|-- backtests/                 # 回测路线和占位
|-- examples/                  # 示例输入
|-- docs/                      # 架构和操作说明
|-- reports/                   # 生成报告，默认忽略
`-- data/                      # 本地日志和缓存，默认忽略
```

## 限制与免责声明

- 本项目只用于数据整理、研究流程、纸面交易复盘和纪律提醒。
- 不提供投资建议，不承诺收益，不自动交易。
- 行情数据可能延迟、缺失、限流或不可用。
- QDII ETF 有溢价、汇率、境外假期和流动性风险。
- A股有 T+1、涨跌停、最小交易单位等限制。
- 任何真实下单都必须由使用者独立确认并手动提交。

## 相关文档

- [架构说明](docs/architecture.md)
- [Agent 职责](agents/README.md)
- [工作流 Demo](workflows/README.md)
- [数据接口](connectors/README.md)
- [策略与风控](strategies/README.md)
- [回测](backtests/README.md)
- [学习摄取](docs/learning_intake.md)
- [iFind 授权与隐私](docs/ifind_auth_and_privacy.md)
- [阿里云 API 使用说明](docs/alicloud_api_usage.md)
- [优秀案例借鉴](docs/reference_cases.md)
- [动作卡实验室](ACTION_CARD_LAB.md)
