# Data Source Upgrade Plan

This project should treat data quality as a first-class risk control layer.
Free public endpoints are useful for prototyping and cross-checking, but they
should not be the only source behind live decision support.

## Target Coverage

| Layer | Target data | Preferred sources | Current role |
| --- | --- | --- | --- |
| A-share market data | Full A-share universe, price, turnover, volume ratio, board, industry, ST/suspension flags | **Galaxy Xingyao AmazingData ✅ (2026-06-18)** / iFinD / Tushare Pro / AKShare | 5,528 A-shares + 1,563 ETFs live |
| ETF and QDII | Price, IOPV/premium, tracking index, holdings, FX and overseas risk | **Xingyao ETF list ✅** / Authorized A-share data, iFinD/Tushare, exchange data | 1,563 ETF codes live; QDII premiums need supplement |
| US ETFs / global assets | US ETF price, holdings, index, pre/post-market, FX | Polygon, Finnhub, Nasdaq Data Link, Morningstar | Needed for Nasdaq/S&P/QDII checks |
| Options | Contract chain, premium, IV, Greeks, volume, OI | Broker option chain, exchange authorized data, **Xingyao option basics ✅** | Basic contract cache live; Greeks/IV need supplement |
| Fundamentals | Financial statements, valuation, forecasts, announcements | **Xingyao InfoData ✅** / iFinD / Tushare Pro / CNINFO | Income/Balance/Cashflow statements live |
| News and sentiment | Announcements, industry news, regulatory risk, negative sentiment | CNINFO, exchange sites, company IR, RSS, Finnhub/Benzinga-style news APIs | Evidence pool only; never direct buy signal |

## Procurement Priority

1. Broker/Galaxy official access: confirm simulated-options account, option-chain
   export, market-data port, QMT/PTrade or other official API availability.
2. A-share authorized market data: solve full-market coverage first.
3. ETF/QDII premium and holdings: needed before chasing Nasdaq/S&P/overseas ETFs.
4. Options chain: replace simulation premium with real option-chain data.
5. Fundamentals and announcements: add earnings and risk-event filters.
6. News/sentiment: add evidence ranking, not trade signals.

Do not purchase Xianyu resale APIs until the seller passes the due-diligence
checklist in `docs/data_vendor_due_diligence.md`. Unofficial access can be
useful for comparison during research, but it should not become the primary
source for live decision support.

## Validation Rules

- Every decision report must show the data source, coverage count, and missing count.
- Any source marked as cache, estimate, or simulation must stay visually separated from real-time quotes.
- Critical price fields should be cross-checked with at least two sources when possible.
- If coverage is below target, the dashboard must downgrade trading confidence.
- Paid data APIs should be wrapped as connectors, with credentials loaded from environment variables only.

## Environment Variables To Add Later

```text
IFIND_ENABLED=false
IFIND_USERNAME=
IFIND_PASSWORD=
TUSHARE_TOKEN=
POLYGON_API_KEY=
FINNHUB_API_KEY=
MORNINGSTAR_API_KEY=
DATA_QUALITY_MIN_A_SHARE_ROWS=5000
```
