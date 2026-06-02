# Public Web Scraping Upgrade

This project can use public web scraping for learning intake, documentation
summaries, and source discovery. It must not scrape private broker clients,
paid data portals, authenticated pages, or pages that disallow crawling.

## Scrapling Intake

`D4Vinci/Scrapling` is useful as a modern scraping framework reference. It has
an active Python project, permissive BSD-3-Clause license, and strong parsing
and fetcher APIs.

Use it here only as an optional public-page fetcher:

- allowed: public docs, public GitHub pages, public articles
- allowed: title/text/link extraction for review reports
- not allowed: bypassing access controls, CAPTCHA, Cloudflare challenges, login
  sessions, broker portals, or paid-market-data pages
- not allowed: unattended high-rate crawling

## Command

Basic fallback mode:

```powershell
python tools\public_web_fetch.py https://github.com/D4Vinci/Scrapling --backend requests
```

Optional Scrapling mode after local installation:

```powershell
pip install scrapling
python tools\public_web_fetch.py https://github.com/D4Vinci/Scrapling --backend scrapling
```

`--backend auto` tries Scrapling first and falls back to `requests`.

## Guardrails

- robots.txt is checked by default.
- private, loopback, and link-local hosts are blocked by default.
- fetched text is capped with `--max-chars`.
- the connector extracts review material only; it does not produce trading
  signals.
