# A-Share Stack Adaptation

This note maps the six-layer Polymarket-style stack from the reference video into the current A-share ETF and stock satellite system.

It is not a recommendation to trade more. The useful part to borrow is the layered process: data, filtering, evidence, execution, risk, and review.

## Current Account Context

Snapshot used by the current repository:

```text
Total monitored capital: 476,255.78
Broker account total: 307,901.59
Broker market value: 160,948.10
Broker available cash: 146,953.49
External cash-like funds: 168,354.19
Deployable cash reference: 308,439.99
No-touch reserve floor: 100,000
Stage 1 active capital: 260,000
ETF/core target inside Stage 1: about 160,000
Short-term stock bucket: 100,000
Maximum new buying in one day: 60,000
```

Current position logic:

```text
ETF core remains the anchor.
Short-term stocks are satellite probes.
B-grade single stock limit: 20,000
A-grade strong confirmation limit: 30,000
Maximum simultaneous short-term stocks: 4
Daily soft stop: -1,200
Daily hard stop: -2,000
Daily 3,000 is a strong-signal-day reference, not a daily task.
```

Current core holdings and rules already in `portfolio.json`:

```text
512100: large ETF core position, close to single-ETF limit; do not add by default.
513130: rebound-exit logic; do not add.
159870: rebound-exit logic; do not add.
512000: small grid/watch position.
588000: small defensive gold position.
518880: defensive gold watch position.
159696 / 513500 / 513310: QDII or high-premium observation; check premium before acting.
600498: prior short-term test completed; re-enter only through the full action-pool process.
```

## Borrowed Six-Layer Structure

### Layer 1: Market Universe

Polymarket version: all markets and events.

A-share version:

```text
ETF core universe:
- 512100, 510300, 510500, 588000, 512760, 512000, 518880, 513130, 159696, 513500, 513310

Theme universe:
- AI digital infrastructure layers in `digital_infra_watchlist.json`

Broad scan:
- Full A-share scan from Eastmoney, filtered by tradability, liquidity, amount, turnover, and no-chase rules.
```

Upgrade:

```text
Add a daily `market_universe_snapshot` section to the JSON report:
- active ETF count
- active theme layer count
- broad candidates count
- blocked names count
- reason for blocking
```

### Layer 2: Quote And Liquidity Data

Polymarket version: order book, bid/ask, spread, depth.

A-share version:

```text
Current implementation:
- latest price
- daily percentage change
- amount
- volume ratio
- turnover
- MA20 / MA60 when available

Missing but useful:
- bid/ask spread
- level-1 order-book pressure
- limit-up / limit-down distance
- opening gap
- intraday high pullback
- whether the stock is one-word limit-up or impossible to enter cleanly
```

Upgrade priority:

```text
1. Keep current quote scan.
2. Add a simple execution-quality score:
   - spread ok
   - amount ok
   - turnover ok
   - not one-word limit-up
   - not a fast spike above no-chase zone
3. Only allow action-pool names when execution quality passes.
```

### Layer 3: Evidence And Theme Confirmation

Polymarket version: event information and market mismatch.

A-share version:

```text
Evidence stack:
- ETF backdrop is not weakening.
- Stock is inside a priority theme layer.
- At least 2-3 names in the same layer are moving together.
- The leader is not the only stock moving.
- Price action is not already overheated.
- There is a catalyst: announcement, order, earnings, policy, price increase, or product milestone.
```

Current system already supports:

```text
Layer matching through `digital_infra_watchlist.json`.
Action pool from broad-market scan.
Focus on AI infrastructure and related satellite themes.
```

Upgrade:

```text
Add `layer_resonance_score`:
- 0: no layer match
- 1: one stock in layer moves
- 2: 2-3 stocks in layer move
- 3: layer leader plus followers move with amount expansion

Only level 2 or 3 can become a real action candidate.
```

### Layer 4: Position Permission

Polymarket version: whether a trade is allowed after pricing and market checks.

A-share version:

```text
Before any buy idea, the system should answer:
- Is this ETF core, grid, exit, or satellite?
- Is the account already near the target weight?
- Is the minimum lot size too large?
- Is it main-board tradable, or does it require ChiNext/STAR/Beijing permission?
- Does today still allow new positions after the daily risk gate?
- Would this exceed the 100,000 short-term bucket?
- Would this exceed the 60,000 max new-buying limit for the day?
```

Current system already has:

```text
Daily soft and hard stop.
Single-stock capital limits.
Minimum lot cost check.
No-chase threshold.
Main-board preference.
```

Upgrade:

```text
Add a `position_permission` object to each action candidate:
- allowed: true/false
- max_capital
- lot_size
- estimated_shares
- blocked_reason
- bucket_after_trade
```

### Layer 5: Execution Plan

Polymarket version: place or skip orders depending on opportunity and depth.

A-share version:

```text
09:10: plan only, no order.
09:40: first decision window.
10:45: confirmation or lower expectation.
14:40: hold, reduce, exit, or carry overnight.
```

Execution rule:

```text
The radar may say "candidate"; it should not say "must buy".
The report should output one clear action card:
- do not trade
- watch only
- B-grade trial, max 20,000
- A-grade trial, max 30,000
- reduce / take profit
- stop loss / exit
```

Upgrade:

```text
Add execution checklist to each action card:
- entry range
- invalidation price
- take-profit reference
- stop-loss reference
- decision window
- reason this is not a chase
```

### Layer 6: Review And Capital Scaling

Polymarket version: track edge, execution quality, and failed opportunities.

A-share version:

```text
Every trade should produce a row:
- planned setup
- actual entry
- actual exit
- whether the layer confirmed
- whether the action followed the report
- P/L
- mistake type
- whether capital can stay the same, shrink, or expand
```

Current scaling gates:

```text
Stage 2 short-term bucket 150,000:
- 20 trading days net positive
- max drawdown below 15,000

Stage 3 short-term bucket 200,000:
- two consecutive profitable months
- no new-trade day losing over 2,000

Shop principal:
- stays outside until the A-share system beats shop cashflow for 3 months with controlled drawdown.
```

Upgrade:

```text
Create `trade_journal.csv` or `trade_journal.json`.
Compute weekly:
- win rate
- average win
- average loss
- max drawdown
- rule violations
- missed trades that were correct to skip
- chased trades
- A-grade vs B-grade outcome
```

## Best Adaptation For The Current Repository

The current system is already close to the right shape. The next upgrade should not be automatic trading. It should be a stronger decision filter:

```text
Current:
full scan -> candidates -> watch/action pool -> email report

Upgrade:
full scan
-> layer resonance score
-> execution quality score
-> position permission
-> A/B/no-trade card
-> journal feedback
```

## Practical Priority

### Priority 1: Make The Report More Like A Trading Desk

Add these fields to `reports/latest.json`:

```text
layer_resonance_score
execution_quality_score
position_permission
decision_card
risk_gate
```

The daily report should answer:

```text
What is strong?
What is actually tradable?
What is forbidden because of position, heat, permission, or risk?
What is the one next action at 09:40 / 10:45 / 14:40?
```

### Priority 2: Separate Current Holdings From New Opportunities

For current holdings:

```text
512100: manage exposure; do not add unless a new ETF-core rule triggers.
513130 / 159870: rebound-exit and reduce logic.
512000: grid/watch only.
518880 / gold: defensive hedge.
QDII names: premium check first.
```

For new opportunities:

```text
Only use the short-term stock bucket.
Only 1-4 names.
Only 20,000 to 30,000 per name.
Only after layer and execution confirmation.
```

### Priority 3: Add A Feedback Loop Before Increasing Capital

Do not scale because the market feels hot. Scale only when the journal proves the process works.

```text
20 valid trades before considering larger size.
No bucket increase without positive net result and controlled drawdown.
No external cash transfer unless a stage gate is passed.
No shop-principal decision before the September checkpoint logic.
```

## One-Sentence Operating Model

Use ETFs to carry the account, use stock satellites only when the layer confirms, use the radar to say no most of the time, and use the journal to decide whether the machine deserves more capital.
