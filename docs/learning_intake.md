# Learning Intake

The radar should improve by studying useful projects and communities, but it should not blindly copy code or outsource decisions.

## Goal

Create a repeatable learning loop:

```text
external project/community
  -> source watchlist
  -> relevance scoring
  -> human review
  -> small experiment
  -> project rule or connector
  -> paper-trade validation
```

## What The System May Absorb

- connector patterns
- backtest metrics
- paper-trading workflows
- risk dashboards
- option-chain analytics
- README and documentation patterns
- evaluation methods for strategy quality

## What The System Must Not Absorb Blindly

- return claims
- trading signals without reproducible data
- private broker protocols
- copied proprietary strategy code
- advice that bypasses risk gates
- social-media hype without testable evidence

## Command

Run a learning intake report:

```powershell
python tools/learning_intake.py --sources examples/learning_sources.json --output reports/learning_intake.md
```

The output is a review document. It is not an instruction to trade.

## Daily Learning Documents

Daily research and tool-learning notes should be saved as:

```text
docs/daily_learning_intake_YYYY-MM-DD.md
```

The daily note must separate:

- what is useful
- where it is useful in the system
- what rule or workflow can be borrowed
- what must not become a trading signal
- which files or modules should be improved next

Current daily notes:

- `docs/daily_learning_intake_2026-06-08.md`

## Review Questions

For each candidate source, ask:

- Does it improve data quality, risk control, backtesting, reporting, or execution discipline?
- Can the idea be tested offline first?
- Does it require credentials, paid data, or broker permission?
- Is it compatible with the no-auto-trading boundary?
- What is the smallest experiment we can run this week?
