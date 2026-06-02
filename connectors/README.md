# Connectors

The project currently keeps connector logic inside `monitor.py` to avoid premature abstraction. This directory documents the connector boundary for future refactoring.

## Current Connectors

| Source | Use | Notes |
| --- | --- | --- |
| Eastmoney | primary quote and broad-market pages | main source for ETF/A-share radar |
| Tencent | single-symbol fallback quote | used when Eastmoney fails |
| Sina | broad-market and single-symbol fallback | useful for A-share fallback scan |
| Yahoo | additional fallback quote path | useful for some ETF symbols |
| Xingyao/AmazingData | optional option basics | requires local SDK path and credentials |
| Public web scraper | optional public-page fetcher | `connectors/public_web_scraper.py`; supports Scrapling if installed and falls back to requests |
| Local files | portfolio, reports, paper journal | deterministic and auditable |

## Connector Principles

- Prefer official APIs, public endpoints, or user-authorized file exports.
- Keep credentials in `.env` or GitHub Secrets.
- Treat missing data as a risk state, not as permission to invent a signal.
- Do not reverse engineer broker private login sessions or market-data channels.
- Do not use scraping tools to bypass access controls, CAPTCHA, Cloudflare
  challenges, paid-data walls, or authenticated broker portals.

## Future Shape

A later refactor can introduce:

```text
connectors/
|-- base.py
|-- eastmoney.py
|-- sina.py
|-- tencent.py
|-- yahoo.py
|-- xingyao.py
|-- public_web_scraper.py
`-- file_exports.py
```

The shared connector output should be a small schema:

```text
code, name, price, pct_change, amount, ma20, ma60, source, timestamp
```
