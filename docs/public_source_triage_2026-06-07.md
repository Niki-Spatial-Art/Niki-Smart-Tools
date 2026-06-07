# Public Source Triage

Date: 2026-06-07

This refresh looked for fresh public research sources that improve the repo's
research workflow without drifting into unattended execution. The selection bar
 stayed the same:

- public and credible
- useful for ETF/A-share monitoring, options research, backtesting, risk
  control, dashboards, or paper-trade review
- compatible with human-in-the-loop execution discipline
- not already covered by stronger existing entries

## Added To Learning Intake

| Source | Layer | Why |
| --- | --- | --- |
| cvxportfolio | ETF allocation and risk budgeting | Adds a research-first portfolio optimization and backtesting framework with explicit transaction costs, leverage constraints, and causality-safe simulation patterns. |
| options_portfolio_backtester | Options research | Adds a focused options-and-equity portfolio backtester with multi-leg presets, contract inventory, and Greeks-aware risk management for simulation-only studies. |
| SSE Stock Options Hub | A-share options reference | Official Shanghai Stock Exchange source for ETF option contracts, rule pages, investor education, and risk-control context. |
| SZSE Options Overview | A-share options reference | Official Shenzhen Stock Exchange options overview and rule entry point for CSI 300 ETF and Shenzhen options product context. |

## Reviewed But Not Added

| Source | Reason |
| --- | --- |
| optopsy | Useful options backtesting library, but the new `options_portfolio_backtester` entry is a stronger fit because it covers portfolio allocation and explicit risk-manager patterns. |
| open-paper-trading-mcp | Interesting simulator architecture, but it is closer to agent-facing execution tooling than this repo's current research-library focus. |
| Vibe-Trading | Strong overall research workspace, but overlapping too much with this repo's own operating model to justify adding it as a source-library dependency. |
| Generic trading-journal repos | Most were either lightly maintained, narrowly scoped, or lower-signal than the existing `AI Trading Journal` reference already in the library. |
| More crypto/live-trading frameworks | The library already has enough architecture references in that category, and extra additions would dilute the research-first boundary. |

## Result

The source library is still centered on:

- public market-data redundancy
- A-share and ETF market structure
- options education and simulation
- backtest robustness
- risk-aware review workflows
- human-confirmed action cards instead of auto-trading
