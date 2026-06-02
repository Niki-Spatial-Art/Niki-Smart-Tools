# Quant Engine And Intraday Execution Roadmap

Purpose: define how external quant engines and execution frameworks fit into
this project without crossing the automatic-trading boundary.

## Core Judgment

QuantConnect Lean belongs in the research/backtest layer. It should not become
the intraday execution layer for A-share trading.

Current workflow:

```text
data -> radar -> action card -> human review -> paper journal -> backtest -> rule update
```

## Open-Source Fit

| Project | Best Layer | Fit |
| --- | --- | --- |
| QuantConnect Lean | research/backtest | useful for standardized strategy validation and portfolio simulation |
| vn.py / VeighNa | paper execution research | close to domestic quant workflows, but use only with paper or explicit human confirmation |
| WonderTrader | advanced execution research | powerful but complex; not first-stage work |
| easytrader | manual-assist research | high automation risk; do not use for unattended live orders |
| ths_trade | execution failure-mode research | study queueing/logging and Tonghuashun client risks; do not run against live accounts |
| THSTrader | UI-state risk research | mobile/simulation automation reference only; useful for documenting focus, screenshot, and stale-state hazards |
| AI Trading Journal | review/journal UX | useful for improving trade diary, AI conversation capture, and post-trade attribution |
| FinGPT | AI research/RAG | useful for sentiment and evidence extraction; never convert model text directly into a trade |
| ai_quant_trade | learning syllabus | broad AI-quant study map; use examples as research prompts, not production modules |
| Microsoft Qlib | AI/factor research | useful for ML/factor experiments, not intraday order operation |

## Project Layers

### 1. Intraday Reminder Layer

Keep the current workstation:

- `monitor.py`
- `tools/ifind_http_probe.py`
- `tools/ifind_position_backtest.py`
- `tools/local_dashboard.py`
- `reports/latest.md`
- `reports/latest.json`

Short-term strengthening:

- 09:10: observe only.
- 09:40: first confirmation, only A/B-grade cards.
- 10:45: continuation check.
- 14:40: risk reduction, stop handling, overnight plan.

### 2. Limit-Up Candidate Radar

The goal is not to promise limit-up trades. The goal is to build a candidate
radar that quickly brings strong names into manual review.

Candidate fields:

- theme match
- money-flow strength
- opening acceptance
- peer resonance
- chase-limit discipline
- ST/new-stock/suspension/liquidity filters

### 3. Backtest Layer

First stage:

1. Convert `reports/latest.json` action cards into standardized signals.
2. Replay T+1, take-profit, and stop-loss rules on historical data.
3. Measure next-day, two-day, and five-day outcomes.
4. Promote only validated rules back into the intraday radar.

### 4. Execution Framework Research

Future vn.py/easytrader/miniqmt work must stay behind these gates:

- paper account first
- human confirmation before any real order
- no automatic scaling to satisfy a profit target
- no bypassing broker or account risk controls
- no screen-clicking or app automation while the workstation is unattended
- every execution experiment must write a journal event before and after the simulated order

### Automation Tool Risk Notes

The latest pasted sources reinforce the same boundary:

- `easytrader`, `ths_trade`, `THSTrader`, `stock-1`, and `AutoTrade` are useful for
  studying broker/client automation failure modes, not for direct deployment.
- UI automation risks include stale windows, lost focus, pop-up dialogs, delayed
  confirmations, wrong account context, and broker client upgrades.
- If execution research is ever resumed, start with simulation, then paper
  account, then a human-confirmed one-click checklist. Never jump to unattended
  live orders.

## Capital Target Handling

Real account size, cash, and targets are private. Public methodology:

1. Convert target into required weekly and monthly return.
2. Compare required return with realistic drawdown tolerance.
3. If the target implies excessive risk, downgrade it to a research target.
4. Scale only after 20-50 trade samples show positive expectancy.

## Not Doing

- no automatic live orders
- no forced trading for monthly targets
- no treating Lean as an intraday emergency tool
- no treating limit-up candidates as buy recommendations
