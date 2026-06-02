# AI Quant Radar & Paper-Trade Review Agent

[![ETF Strategy Monitor](https://github.com/Niki-Spatial-Art/Niki-Smart-Tools/actions/workflows/monitor.yml/badge.svg)](https://github.com/Niki-Spatial-Art/Niki-Smart-Tools/actions/workflows/monitor.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![No Auto Trading](https://img.shields.io/badge/no%20auto%20trading-human%20review%20required-orange)](#limitations--disclaimer)

A lightweight quant research and trading-discipline radar for ETFs, A-shares, option watchlists, paper-trade journaling, and human-reviewed strategy reports.

This project is best understood as a **hybrid AI quant radar**: it combines market-data connectors, signal/risk rules, portfolio-aware action cards, optional AI summaries, email alerts, and a local browser dashboard. It does not place orders and it does not provide investment advice.

## Who It Is For

- Individual investors who want a disciplined daily ETF/A-share watchlist instead of impulse trading.
- Quant learners who want a small Python project for market-data ingestion, rule-based signals, paper-trade logging, and report generation.
- Researchers who want a practical workflow skeleton inspired by financial-services agent design: task-specific agents, clear data connectors, workflow stages, and human review gates.
- Users who need local Windows scheduled runs plus GitHub Actions fallback monitoring.

## Project Positioning

The codebase is primarily a **quant project**, not a corporate finance workflow agent.

It focuses on:

- market data and quote source rotation
- ETF, A-share, AI infrastructure, and option-related radar logic
- rule-based signals and action cards
- portfolio sizing, risk gates, and T+1 discipline
- paper-trade audit logs
- reports, email delivery, and a local browser dashboard

A clearer GitHub label for the project is:

> **AI Quant Radar Agent for ETF/A-share monitoring, paper-trade review, and human-approved execution discipline.**

## Core Features

- **Market data connectors**: Eastmoney, Tencent, Sina, Yahoo fallback quotes, and optional Galaxy Xingyao/AmazingData option basics.
- **Signal engine**: ETF green/yellow/red labels, broad A-share scan, AI digital infrastructure watchlist, option simulation radar, and action-card generation.
- **Risk controls**: QDII premium caution, high-risk code blocks, no-chase rules, daily loss gates, target position checks, and T+1 reminders.
- **Human review gates**: every action card is a paper plan first; the user must fill actual entry/exit details before any result is counted.
- **Report agent**: Markdown, JSON, HTML email, and a local dashboard at `http://localhost:8501`.
- **Learning intake**: curated open-source/community sources can be scored into a review report before ideas enter the strategy backlog.
- **Quant engine roadmap**: Lean/QuantConnect is tracked as a research/backtest layer, while vn.py/easytrader-style tools are evaluated separately for human-approved intraday execution.
- **Automation**: GitHub Actions schedule, Windows Task Scheduler scripts, and a 09:00 local action-card audit.

## Agent Design

The project follows an agent/workflow style without adding a heavy framework.

| Agent | Current implementation | Responsibility |
| --- | --- | --- |
| Market Data Agent | `monitor.py`, `scraper.py` | Fetch and normalize ETF, A-share, option, and portfolio inputs. |
| Signal Research Agent | `monitor.py`, `digital_infra_watchlist.json` | Classify ETFs/stocks, scan AI infrastructure layers, build candidate pools. |
| Risk Agent | `monitor.py`, `portfolio.json` | Apply no-chase, drawdown, cash, position, QDII, and T+1 gates. |
| Action Card Agent | `monitor.py`, `tools/action_audit.py` | Convert signals into paper-trade plans and journal rows. |
| Report Agent | `monitor.py`, `emailer.py`, `tools/local_dashboard.py` | Generate Markdown/JSON/HTML reports, email alerts, and browser dashboard views. |
| Human Review Gate | `data/paper_trade_journal.csv` | Requires manual fill-in of execution details and review notes. |

See [docs/architecture.md](docs/architecture.md) for the full workflow map.
See [docs/quant_engine_and_intraday_execution_roadmap.md](docs/quant_engine_and_intraday_execution_roadmap.md) for the Lean research-layer and intraday execution-layer roadmap.

## Workflow Example

```text
Data connectors
  -> quote normalization
  -> ETF/A-share/option radar
  -> signal classification
  -> risk gates and sizing
  -> action cards
  -> paper journal
  -> report/email/dashboard
  -> human review
```

Run the offline demo in 5-10 minutes:

```powershell
python workflows/demo_quant_research.py
```

It uses [examples/sample_latest_report.json](examples/sample_latest_report.json), exports sample action cards into a temporary journal, summarizes the paper plan, and prints the same kind of morning review message used by the local audit task.

## Installation

```powershell
git clone https://github.com/Niki-Spatial-Art/Niki-Smart-Tools.git
cd Niki-Smart-Tools
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create local settings:

```powershell
Copy-Item .env.example .env
Copy-Item portfolio.example.json portfolio.local.json
notepad .env
notepad portfolio.local.json
```

`portfolio.local.json` is for private account size, positions, cash policy, and
risk limits. It is ignored by git. The committed `portfolio.json` and
`portfolio.example.json` are sanitized examples only.

Minimum email settings:

```text
SENDER_EMAIL=your_qq_email@qq.com
SENDER_PASSWORD=your_qq_smtp_authorization_code
RECIPIENT_EMAIL=your_receive_email@qq.com
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
```

Optional AI summary settings:

```text
AI_ENABLED=true
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=your_dashscope_api_key
```

Optional private portfolio setting:

```text
PORTFOLIO_FILE=portfolio.local.json
```

## Running Locally

Generate the main radar report:

```powershell
python monitor.py
```

Export latest action cards into the paper-trade journal:

```powershell
python tools/action_audit.py export-plan --report reports/latest.json --journal data/paper_trade_journal.csv
```

Summarize closed paper trades:

```powershell
python tools/action_audit.py summarize --journal data/paper_trade_journal.csv
```

Start the local browser dashboard:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard_local.ps1
```

Then open:

```text
http://localhost:8501
```

Build a learning-intake report from curated projects and communities:

```powershell
python tools/learning_intake.py --sources examples/learning_sources.json --output reports/learning_intake.md
```

Build the local daily target card from the latest report and review samples:

```powershell
python tools/daily_target_card.py --report reports/latest.json --review data/trade_review_samples.csv --output reports/daily_target_card.md
```

Run the full local research/report stack and generate one aggregate HTML report:

```powershell
python tools/full_system_rerun.py
```

Reuse existing local report inputs and send one aggregate email:

```powershell
python tools/full_system_rerun.py --skip-monitor --no-network-learning --email
```

Send the learning-intake report by email:

```powershell
python tools/learning_intake.py --sources examples/learning_sources.json --output reports/learning_intake.md --email
```

Install the Windows 09:00 action-card audit task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_action_audit_0900_task.ps1
```

## GitHub Actions

Manual run:

```text
Actions -> ETF Strategy Monitor -> Run workflow
```

Scheduled runs are configured in `.github/workflows/monitor.yml` for Beijing trading-session checkpoints.
`.github/workflows/action-audit.yml` sends a 09:00 paper-plan review email.
`.github/workflows/learning-intake.yml` sends a weekly source-learning report.
`.github/workflows/ci.yml` runs a Python compile smoke test and the offline demo.

Required GitHub secrets:

```text
SENDER_EMAIL
SENDER_PASSWORD
RECIPIENT_EMAIL
```

Optional secrets:

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

## Example Outputs

Reports are archived locally when `monitor.py` runs:

```text
reports/YYYY-MM/YYYY-MM-DD_HHMMSS_etf_radar.md
reports/YYYY-MM/YYYY-MM-DD_HHMMSS_etf_radar.json
reports/latest.md
reports/latest.json
```

Action-card journal:

```text
data/paper_trade_journal.csv
```

Typical action-card fields:

```text
code, name, decision, grade, planned_capital, planned_shares,
entry_low, entry_high, take_profit_1, take_profit_2, stop_loss,
risk_gate, reason, actual_entry_price, actual_exit_price, review
```

## Project Structure

```text
.
|-- monitor.py                 # Main quant radar and report workflow
|-- ai_client.py               # Optional OpenAI-compatible summary client
|-- emailer.py                 # SMTP email delivery
|-- portfolio.json             # Sanitized public example
|-- portfolio.example.json     # Template for private local configuration
|-- portfolio.local.json       # Private local portfolio file, ignored by git
|-- digital_infra_watchlist.json
|-- tools/
|   |-- action_audit.py        # Paper-trade export, notify, summarize
|   `-- local_dashboard.py     # Standard-library local browser dashboard
|-- agents/                    # Agent role docs
|-- workflows/                 # Workflow docs and runnable demos
|-- connectors/                # Data connector docs
|-- strategies/                # Strategy/risk rule docs
|-- backtests/                 # Backtest roadmap and placeholders
|-- examples/                  # Small demo inputs
|-- docs/                      # Architecture and operating notes
|-- reports/                   # Generated reports, ignored by git
`-- data/                      # Local journals/caches, mostly ignored by git
```

## Security & Privacy

- Keep secrets in `.env` or GitHub Secrets only.
- Keep real account values, broker snapshots, iFind probe outputs, generated dashboards, and logs in ignored local files.
- `data/` is ignored except for `data/README.md` and `data/.gitkeep`.
- `portfolio.local.json` and `*.local.json` are ignored.
- See [SECURITY.md](SECURITY.md) before publishing changes or adding broker/data-provider integrations.

## Roadmap

- Add a formal backtest module for action-card hit rate, stop-loss behavior, and T+1 exits.
- Add a connector interface so Eastmoney, Sina, Tencent, Yahoo, and authorized broker exports share one schema.
- Add option-chain analytics for implied volatility, expiry selection, and simulated exercise workflows.
- Add risk dashboards for drawdown, exposure by theme, QDII premium, and single-name concentration.
- Add CSV/TXT import from authorized broker or exchange data exports if available.
- Add structured evaluation reports for AI summaries so the model remains a reviewer, not a signal source.
- Add a weekly learning-intake automation that reviews new open-source tools and community pain points before promoting anything into strategy experiments.

## Limitations & Disclaimer

- This project is for data organization, research workflow, paper-trade review, and trading-discipline reminders only.
- It does not provide investment advice, return promises, or automated trading.
- Public market data can be delayed, incomplete, rate-limited, or unavailable.
- QDII ETFs can carry premium/discount, FX, holiday, and liquidity risks.
- A-share execution has T+1 constraints and lot-size rules.
- Any real order must be independently reviewed and submitted by the user.

## Related Docs

- [Architecture](docs/architecture.md)
- [Agents](agents/README.md)
- [Workflow demo](workflows/README.md)
- [Connectors](connectors/README.md)
- [Strategies](strategies/README.md)
- [Backtests](backtests/README.md)
- [Learning intake](docs/learning_intake.md)
- [Action Card Lab](ACTION_CARD_LAB.md)
