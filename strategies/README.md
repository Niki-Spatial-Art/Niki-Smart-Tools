# Strategies

This project uses rules and paper-trade review before adding complex strategy engines.

## Current Strategy Families

### ETF Radar

Purpose:

- monitor ETF trend state
- flag QDII/high-premium risk
- prevent narrative-driven chasing

Main file:

- `monitor.py`

### AI Digital Infrastructure Radar

Purpose:

- scan A-share candidates linked to AI infrastructure layers
- separate theme resonance from single-stock noise
- keep short-term action cards inside portfolio/risk limits

Main files:

- `monitor.py`
- `digital_infra_watchlist.json`

### Option Simulation Radar

Purpose:

- estimate option payoff/risk around ETF underlyings
- support beginner education and review
- avoid treating options as a shortcut to leverage

Main file:

- `monitor.py`

### Action Card Paper Trading

Purpose:

- convert a candidate into a structured paper plan
- require manual follow-up before performance is counted

Main files:

- `tools/action_audit.py`
- `templates/trade_journal_template.csv`

### Intraday Execution Layer Research

Purpose:

- study how to turn real-time radar output into faster human-reviewed action cards
- evaluate vn.py, WonderTrader, and easytrader-style tooling without connecting automatic live orders
- define limit-up candidate scoring and 09:40/10:45/14:40 execution discipline

Main file:

- `strategies/intraday_execution_layer_research.md`

## Strategy Rules

- A green signal is permission to study, not permission to buy.
- A red signal blocks action.
- A zero-capital or zero-share card is observation only.
- For A-share short-term trades, planned trade amount below 10,000 CNY is blocked by default.
- For A-share short-term trades, planned trade amount between 10,000 and 20,000 CNY is discouraged unless the card is A-grade and exit liquidity is clear.
- T+1 constraints must be visible on every A-share action card.
- Actual execution is outside the system and must be reviewed by the user.
