# ETF Strategy Monitor Overview

## Positioning

ETF Strategy Monitor is a personal trading-discipline assistant for ETF investors.

It is designed for a lightweight workflow:

```text
Market data -> Rule engine -> AI summary -> Email alert -> Manual decision
```

The project does not place orders automatically. It helps the user avoid emotional decisions, especially chasing high-premium or overheated ETF products.

## Core Ideas

1. Use ETF watchlists instead of scattered manual checking.
2. Use rule-based red/yellow/green signals before asking AI to summarize.
3. Treat extreme products such as `513310` as risk samples unless premium and crowding cool down.
4. Keep all credentials in GitHub Secrets.
5. Return success when external data sources fail, so GitHub Actions does not send noisy failure emails.

## Current Modules

```text
monitor.py      ETF radar, Eastmoney data fetch, signal rules, email report
ai_client.py    OpenAI-compatible AI summary client
emailer.py      SMTP email sender
requirements.txt
.github/workflows/monitor.yml
```

Old bank-rate scraping code remains in `scraper.py` for reference, but the active entry point is now ETF-focused through `monitor.py`.

## Signal Model

Green:

- Price is above 20-day and 60-day moving averages
- No obvious single-day overheating
- Not on the high-risk watchlist

Yellow:

- Worth observing but not comfortable enough to chase
- Trend is incomplete, price is below the 20-day line, or daily move is already large

Red:

- High-risk code such as `513310`
- Daily move is too hot
- Premium/risk-warning logic flags it

## Sharing Angle

The project is useful as a public example of:

- GitHub Actions for personal investing workflows
- AI-assisted trading discipline
- ETF watchlist automation
- Low-cost lightweight quant tooling

The clean slogan:

```text
ETF 主线雷达，不是荐股工具，是交易纪律工具。
```
