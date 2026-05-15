# ETF Strategy Monitor

一个用 GitHub Actions 跑起来的轻量 ETF 主线雷达。

它不是荐股工具，也不承诺收益；它的定位是帮个人投资者把交易纪律自动化：每天扫描重点 ETF，识别趋势、过热、QDII 溢价和高风险标的，然后用 AI 生成一封简短策略邮件。

## What It Does

- 自动监控 ETF 主线池
- 用东方财富、腾讯、新浪等公开行情源读取价格
- 计算日内涨跌幅、风险标签和组合执行动作
- 输出绿色 / 黄色 / 红色交易纪律信号
- 默认把 `513310` 作为高溢价风险样本，提示只看不追
- 支持千问、Kimi、DeepSeek 等 OpenAI-compatible API 生成 AI 简报
- 通过 GitHub Actions 免费运行
- 通过 GitHub Secrets 保存邮箱和模型 API Key

## Signal Rules

| Signal | Meaning | Discipline |
| --- | --- | --- |
| Green | 趋势偏强且没有明显过热 | 可研究小仓或按网格执行 |
| Yellow | 有主线热度，但位置或趋势不够舒服 | 观察，不追 |
| Red | 高溢价、风险公告、单日过热或情绪拥挤 | 禁止追买 |

系统核心不是预测涨跌，而是减少冲动交易：不追高溢价 ETF，不把情绪样本当买入信号，不在数据源失败时制造无意义告警。

## Default Watchlist

```text
513310 中韩半导体ETF
159696 纳指100ETF
510300 沪深300ETF
510500 中证500ETF
512100 中证1000ETF
512880 证券ETF
588000 科创50ETF
512760 半导体ETF
513180 恒生科技ETF
518880 黄金ETF
```

可以通过 GitHub Secrets 或 workflow 环境变量覆盖：

```text
ETF_WATCHLIST=513310,159696,510300,512100,512880
ETF_HIGH_RISK_CODES=513310
ETF_QDII_CODES=513310,159696,513180
```

## Portfolio Rules

`portfolio.json` 把雷达变成执行清单。

它可以定义：

- 总资金和现金
- 当前 ETF 份额和成本
- 目标仓位
- 买入线
- 止盈线
- 止损线
- 默认买入金额

邮件会展示：

```text
买 / 卖 / 等 / 禁止买入
建议金额
当前仓位
目标金额
触发原因
```

## AI Digital Infrastructure

桌面四个录屏里的核心判断已经整理成“AI 数字基础建设”产业链雷达：

- AI 普及以后，瓶颈不会只在 GPU
- 算力负载提高后，压力会扩散到服务器、网络、存储、散热、电力和数据中心
- `513310` 的爆发说明市场会给“稀缺主线 + 跨境稀缺资产 + 情绪拥挤”极高定价
- 但追高溢价 ETF 风险大，下一步更适合做“ETF 核心仓 + 个股卫星仓”

详细分层见：

[AI_DIGITAL_INFRASTRUCTURE_MAP.md](AI_DIGITAL_INFRASTRUCTURE_MAP.md)

机器可读监控池见：

[digital_infra_watchlist.json](digital_infra_watchlist.json)

## v2 Planning Doc

完整的 v2 需求说明、交易纪律规则和 AI 提示词见：

[ETF_Strategy_Monitor_v2_REQUIREMENTS.md](ETF_Strategy_Monitor_v2_REQUIREMENTS.md)

## AI Provider

推荐先用阿里百炼千问：

```text
AI_ENABLED=true
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=your_key
```

也支持：

```text
AI_PROVIDER=kimi
KIMI_API_KEY=your_key
```

```text
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
```

Secrets 不要写进代码，统一放到 GitHub repository secrets。

## GitHub Secrets

必需：

```text
SENDER_EMAIL
SENDER_PASSWORD
RECIPIENT_EMAIL
```

AI 可选：

```text
AI_ENABLED
AI_PROVIDER
DASHSCOPE_API_KEY
KIMI_API_KEY
DEEPSEEK_API_KEY
```

## Run

GitHub Actions 页面手动运行：

```text
Actions -> ETF Strategy Monitor -> Run workflow
```

本地测试：

```text
pip install -r requirements.txt
python monitor.py
```

本地 Windows 定时兜底：

```text
1. 复制 .env.example 为 .env
2. 在 .env 里填邮箱授权码和 AI Key
3. 用 Windows 任务计划程序定时运行 run_monitor_local.ps1
```

推荐本地定时时间：

```text
09:45
11:35
14:50
21:30
```

GitHub Actions 的 schedule 可能延迟或漏跑；本地 Windows 定时更适合准点提醒。

## Disclaimer

本项目只做数据整理、风险提示和交易纪律提醒，不构成投资建议。ETF 有波动风险，QDII ETF 还可能存在溢价、汇率、时差和停牌风险。任何买卖决策都需要使用者自行判断和承担结果。
