# Project Memory

## Purpose

Niki Smart Tools is a local-first A-share/ETF research and decision-discipline workspace. It must never connect to a broker or place orders.

## Important Paths

- Main radar: `monitor.py`
- Dashboard generator: `tools/local_dashboard.py`
- Local market route: `tools/a_stock_market_data.py` and `tools/a_stock_radar_snapshot.py`
- Private runtime data: `data/` and `portfolio.local.json` (ignored by Git)

## Current Safety Rules

- New entries require: complete broad-market scan, fresh valid local broker snapshot, and fresh local A-share route snapshot.
- Existing holdings can still be reviewed while the new-entry gate is blocked.
- The market route is Tencent quote -> TDX/mootdx daily bars -> Tencent qfq daily bars -> AKShare fallback.
- `requirements-a-stock.txt` pins the optional full route (`mootdx`, `akshare`, `pandas`, `stockstats`). `A_STOCK_PYTHON` may point the local launcher to a prebuilt isolated environment.
- `data/broker_account_snapshots.json` is historical and may be malformed; use `data/broker_account_snapshots.local.json` for current manual snapshots.
- The local dashboard is named "Niki 投资决策工作台". Its default order is account snapshot -> holding risk -> market observation -> post-close research.
- The dashboard must visibly downgrade stale broker snapshots; never treat an old screenshot as a current executable position.
- Options are research/simulation only and do not appear in the daily dashboard flow. Xingyao is local optional research; iFind is off by default. Neither belongs in the default refresh path or GitHub Actions.
- GitHub Actions only creates a public A-share market-snapshot artifact. It must not receive broker snapshots, Xingyao credentials, or private account data.

## Local Commands

- `./run_a_stock_radar.ps1`
- `./run_investment_workbench.ps1`
- `./run_monitor_local.ps1`
- `python tools/local_dashboard.py`

## Validation

- Use `python -m py_compile monitor.py tools/a_stock_market_data.py tools/a_stock_radar_snapshot.py tools/local_dashboard.py`.
- Run `python tools/pre_publish_check.py --include-untracked` before committing.
