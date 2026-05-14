# ETF Strategy Monitor

一个用 GitHub Actions 跑起来的轻量 ETF 主线雷达。

它不是荐股工具，也不承诺收益；它的定位是帮个人投资者把交易纪律自动化：每天扫描重点 ETF，识别趋势、过热、QDII 溢价和高风险标的，然后用 AI 生成一封简短策略邮件。

## What It Does

- 自动监控 ETF 主线池
- 用东方财富公开行情接口读取价格和日 K
- 计算 20 日线、60 日线和日内涨跌幅
- 输出绿色 / 黄色 / 红色交易纪律信号
- 默认把 `513310` 作为高溢价风险样本，提示只看不追
- 支持千问、Kimi、DeepSeek 等 OpenAI-compatible API 生成 AI 简报
- 通过 GitHub Actions 免费运行
- 通过 GitHub Secrets 保存邮箱和模型 API Key

## v2 Planning Doc

完整的 v2 需求说明、交易纪律规则和 AI 提示词见：

[ETF_Strategy_Monitor_v2_REQUIREMENTS.md](ETF_Strategy_Monitor_v2_REQUIREMENTS.md)

## Signal Rules

| Signal | Meaning | Discipline |
| --- | --- | --- |
| Green | 趋势偏强且没有明显过热 | 可研究小仓或按网格执行 |
| Yellow | 有主线热度但位置或趋势不够舒服 | 观察，不追 |
| Red | 高溢价、风险公告、单日过热或情绪拥挤 | 禁止追买 |

这套系统的核心不是预测涨跌，而是减少冲动交易：不追高溢价 ETF，不把情绪样本当买入信号，不在数据源失败时制造无意义告警。

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

你可以通过 GitHub Secrets 或 workflow 环境变量覆盖：

```text
ETF_WATCHLIST=513310,159696,510300,512100,512880
ETF_HIGH_RISK_CODES=513310
ETF_QDII_CODES=513310,159696,513180
```

## Portfolio Rules

`portfolio.json` turns the radar into an execution checklist.

It can define:

- total capital and cash
- current ETF shares and cost
- target weight
- buy-below line
- sell-above line
- stop-loss line
- default buy amount

Example:

```json
{
  "total_capital": 480000,
  "cash": 80000,
  "max_single_weight": 0.25,
  "default_buy_amount": 10000,
  "positions": [
    {
      "code": "512100",
      "name": "中证1000ETF",
      "cost": 3.55,
      "shares": 10000,
      "target_weight": 0.15,
      "buy_below": 3.50,
      "sell_above": 3.80,
      "stop_loss": 3.25
    }
  ]
}
```

The email report will show:

```text
买 / 卖 / 等
建议金额
当前仓位
目标金额
触发原因
```

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

```bash
pip install -r requirements.txt
python monitor.py
```

## Disclaimer

本项目只做数据整理、风险提示和交易纪律提醒，不构成投资建议。ETF 有波动风险，QDII ETF 还可能存在溢价、汇率、时差和停牌风险。任何买卖决策都需要使用者自行判断和承担结果。
