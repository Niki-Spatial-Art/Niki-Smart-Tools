# Niki Smart Tools 系统功能集合

更新日期：2026-06-02

## 当前结论

现在系统已经更新到最新一版。新增的量化、AI 交易、撮合引擎、交易看板、学习项目，已经进入系统的学习源和筛选文档；不适合进入核心链路的项目，也已经明确标注为“只观察 / 只学习 / 不接入实盘”。

这套系统现在的定位不是自动交易机器人，而是：

> ETF / A 股 / 期权仿真 / 学习源 intake / 行动卡 / 纸面复盘 / 邮件提醒 / 本地仪表盘 的一体化量化雷达。

核心边界仍然保持：

- 不自动下实盘订单
- 不把 AI 文本直接变成买卖指令
- 不把加密货币合约信号搬进 A 股流程
- 不把撮合引擎接入个人交易链路
- 所有行动卡先进入纸面计划，再由人确认

## 总工作流

```text
数据源
  -> 行情标准化
  -> ETF / A 股 / 期权仿真雷达
  -> 信号分类
  -> 风控门槛和仓位检查
  -> 行动卡
  -> 纸面交易日志
  -> 学习源 intake
  -> Markdown / JSON / HTML 报告
  -> GitHub Actions 邮件
  -> 人工复盘
```

## 已有核心模块

| 模块 | 主要文件 | 当前作用 |
| --- | --- | --- |
| 主雷达 | `monitor.py`, `scraper.py` | 生成 ETF、A 股、QDII、期权仿真相关雷达。 |
| 数据源连接 | `connectors/`, `tools/eastmoney_probe.py`, `tools/ifind_http_probe.py`, `tools/xingyao_data_probe.py`, `tools/yuheng_probe.py` | 管理东方财富、腾讯、新浪、Yahoo、iFind、星耀/AmazingData、玉衡、公开网页抓取等边界。 |
| 信号与风控 | `monitor.py`, `portfolio.json`, `digital_infra_watchlist.json` | 执行不追高、现金纪律、仓位控制、QDII 风险、T+1 约束、止损门槛。 |
| 行动卡 | `monitor.py`, `tools/action_audit.py`, `ACTION_CARD_LAB.md` | 生成入场区间、止损、止盈、计划资金、计划股数和纸面日志行。 |
| 纸面日志 | `data/paper_trade_journal.csv` | 本地忽略文件，用于手动记录模拟/实际复盘，不提交到 GitHub。 |
| 报告输出 | `reports/latest.md`, `reports/latest.json`, `reports/full_system_rerun.html` | 本地或 GitHub Actions 生成，报告目录不提交。 |
| 邮件系统 | `emailer.py`, `tools/full_system_rerun.py`, GitHub Secrets | 发送主雷达、行动卡审计、学习源报告、全系统集合邮件。 |
| 本地仪表盘 | `tools/local_dashboard.py`, `run_dashboard_local.ps1` | 在 `http://localhost:8501` 查看最新雷达、行动卡、期权仿真、学习源预览。 |
| 学习源 intake | `tools/learning_intake.py`, `examples/learning_sources.json`, `docs/learning_intake.md` | 对 GitHub/社区/文章来源打分，先学习筛选，再进入策略研究。 |
| 公开网页抓取 | `connectors/public_web_scraper.py`, `tools/public_web_fetch.py`, `docs/public_web_scraping.md` | 可选 Scrapling，默认 requests fallback，只抓公开页面。 |
| 全系统重跑 | `tools/full_system_rerun.py`, `.github/workflows/full-system-rerun.yml` | 一次性运行主雷达、行动卡导出、日志汇总、学习源 intake、公开网页抓取验证，并发邮件。 |
| CI 检查 | `.github/workflows/ci.yml`, `tools/pre_publish_check.py` | Python 编译检查、离线 demo、发布前敏感文件扫描。 |

## GitHub Actions 自动化

| 工作流 | 文件 | 作用 |
| --- | --- | --- |
| CI | `.github/workflows/ci.yml` | 编译 smoke test 和离线行动卡 demo。 |
| ETF Strategy Monitor | `.github/workflows/monitor.yml` | 定时或手动生成市场雷达邮件。 |
| Action Audit | `.github/workflows/action-audit.yml` | 09:00 纸面行动卡审计邮件。 |
| Learning Intake | `.github/workflows/learning-intake.yml` | 每周学习源报告邮件。 |
| Full System Rerun | `.github/workflows/full-system-rerun.yml` | 手动全功能重跑，发送集合邮件。 |

## 最新加入学习源的项目

这批已经加入 `examples/learning_sources.json` 和筛选文档：

- `Qbot`：AI 量化平台参考，研究、回测、可视化流程学习用。
- `MilleXi stock_trading`：LSTM + 强化学习教学样例，只做实验设计参考。
- `czsc`：缠论分型、笔、信号研究，跟踪上游 `waditu/czsc`。
- `SmartStock-AI-Kit`：桌面盯盘终端、语音提醒、紧凑看板 UX 参考。
- `CCXT`：加密交易所统一接口，作为连接器抽象参考，不接 A 股执行。
- `BingoCrypto Binance Futures Dashboard`：监控看板 UX 参考，不复制合约信号。
- `TradeMatcher match-engine`：Java 撮合引擎架构阅读。
- `lightning-engine`：Go 内存撮合和结算边界架构阅读。

## 明确不进入核心链路的项目

这些已经记录为谨慎项：

- `CtpSystem`：较老的 CTP/上期所学习项目，偏执行且维护风险高。
- `PyTradingSystem`：早期交易系统骨架，规模太小，不作为核心依赖。
- `nof1.ai-AI-trading-agent`：浏览器 AI 加密自动交易 demo，只做 UI/风险提醒。
- 过期 `czsc` fork：不跟踪镜像 fork，只跟踪上游。
- 交易所源码包、撮合引擎：只读架构，不接个人交易链路。

## 常用命令

运行主雷达：

```powershell
python monitor.py
```

运行全系统但不发邮件：

```powershell
python tools/full_system_rerun.py
```

运行全系统并发送集合邮件：

```powershell
python tools/full_system_rerun.py --email
```

生成学习源报告：

```powershell
python tools/learning_intake.py --sources examples/learning_sources.json --output reports/learning_intake.md
```

打开本地仪表盘：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard_local.ps1
```

## 现在系统是否全部更新完

是。当前系统已经把这几轮新增内容整理进：

- 学习源清单
- GitHub 量化项目筛选文档
- 量化引擎与盘中执行边界路线图
- 全系统重跑邮件
- 本系统功能集合文档

最终形态是：

```text
观察 -> 分析 -> 风控 -> 行动卡 -> 纸面日志 -> 复盘 -> 学习 -> 更新规则
```

