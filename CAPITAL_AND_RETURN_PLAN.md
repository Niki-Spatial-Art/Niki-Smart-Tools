# Capital And Return Plan

This file records the full capital picture and the return target used by the ETF and AI stock radar.

It is a planning document, not a promise of return and not a reason to increase risk without evidence.

## Current Capital Picture

Snapshot date: 2026-05-18

| Bucket | Amount | Role |
| --- | ---: | --- |
| Trading account and cash-like funds | 473,903.52 | Current investable base for ETF core and short-term stock satellite radar |
| Family shop investment principal | 700,000.00 | Off-platform fixed cashflow asset, not counted as trading cash in 2026 |
| Shop monthly cashflow | 3,000.00 | About 5.14% implied annual yield on 700,000 |
| Planned monthly new money | 10,000.00 | Added to trading capital from 2026-06 through 2026-12 |

## 2026 Year-End Projection

Assumptions:

```text
Current trading capital: 473,903.52
Monthly new money: 10,000 x 7 = 70,000
Shop cashflow: 3,000 x 7 = 21,000
Base year-end capital before market profit: 564,903.52
```

Return ladder for the 2026 trading capital:

| Market case | Return on current trading capital | Market profit | Year-end capital including new money and shop cashflow |
| --- | ---: | ---: | ---: |
| Defensive / repair year | 8% | 37,912.28 | 602,815.80 |
| Base active target | 15% | 71,085.53 | 635,989.05 |
| Strong but controlled | 20% | 94,780.70 | 659,684.22 |
| Strong-market sprint | 30% | 142,171.06 | 707,074.58 |

This target is aggressive. It can only be pursued when market evidence supports it:

```text
1. AI main line is confirmed by ETF strength.
2. Leading stocks and same-layer stocks move together.
3. Volume expands without extreme crowding.
4. Orders, earnings, price increases, or product milestones support the move.
5. No single position is enlarged only because the annual target has not been reached.
```

## 2027 Scenario If Shop Principal Returns

If the 700,000 shop principal returns in 2027, the projected investable base before 2026 market profit is:

```text
564,903.52 + 700,000 = 1,264,903.52
```

Return ladder:

| Return | Profit | Meaning |
| ---: | ---: | --- |
| 10% | 126,490.35 | Better than current shop cashflow, relatively steady improvement |
| 15% | 189,735.53 | Good active-investing target |
| 20% | 252,980.70 | Offensive target with discipline |
| 30% | 379,471.06 | Strong-market target, requires trend confirmation and higher volatility tolerance |

## Allocation Policy

For a strong-market sprint, the portfolio should still be built as a combination, not a single-stock bet.

```text
ETF core: 50%-60%
Short-term stock satellite: 20%-30%
Cash buffer: 10%-25%
Single stock initial weight: 0.5%-1%
Single stock confirmed max weight: 3%-5%, exceptional confirmed max 8%
```

ETF core role:

```text
1. Carry the long-term beta and trend exposure.
2. Avoid single-stock blowups.
3. Keep the account anchored when short-term satellites are wrong.
4. Main vehicles: broad ETF, technology ETF, semiconductor/AI ETF, QDII growth ETF, gold/defensive ETF.
```

Short-term satellite role:

```text
1. Capture short bursts from policy, earnings, product milestones, and same-layer resonance.
2. Each first position is a probe, not a belief.
3. Add only after the layer confirms; never add only because a daily candle is exciting.
4. Missed first candle is not a mistake. Chasing after missing is the mistake.
```

Priority short-term tracks:

```text
1. Optical modules / CPO / communication switching
2. Photonic computing / silicon photonics / CPO / optical interconnect
3. Hubei Optics Valley / optical modules / storage / materials
4. PCB / copper foil / CCL / high-speed materials
5. Compute-in-memory / near-data compute / HBM storage
6. Domestic AI chips / AI servers / liquid cooling and power
7. Semiconductor equipment / OLED large-panel equipment
8. Humanoid robotics / reducers / servo / sensors
9. Low-altitude economy / drones / eVTOL / air traffic control
10. Commercial space / satellite internet / navigation and remote sensing
11. AI applications / office software / education / content / fintech
12. Green power operators / compute-power coordination / green certificate and green electricity trading
```

Daily operating rhythm:

```text
09:10 Pre-market plan: read candidates, risk notes, and position limits. Do not place an order.
09:45 Opening scan: do not chase the first spike.
10:45 Resonance scan: at least 2-3 names in one layer must confirm.
13:45 Continuation scan: check whether morning strength survives.
14:40 Execution window: only act on pre-defined buy, sell, or reduce rules.
```

## Quant Reference Architecture

Reference date: 2026-05-19

This system should learn the structure of professional quantitative firms, not try to copy their scale. A personal account cannot compete with institutional low latency, financing, full market data, or execution infrastructure. The useful part to copy is the process discipline.

Lingjun-style lessons for this account:

```text
1. Multi-cycle signals: keep short, medium, and long signals separate.
2. Factor expansion: combine price/volume with fundamentals, news, announcements, research notes, and policy signals.
3. AI as research assistant: use AI to summarize filings, news, sector resonance, and rule violations, not to override risk controls.
4. Three-line defense: strategy risk, trading/execution risk, and operations risk must all pass before a trade.
5. Talent loop for one person: after each trade, write the setup, execution, result, and mistake; this is the personal version of researcher training.
```

XTX-style lessons for this account:

```text
1. Prediction first: every candidate needs an expected direction, expected holding period, and invalidation condition.
2. Execution quality matters: avoid chasing wide spreads or emotional spikes; use limit orders and predefined windows.
3. Risk inventory: every open position is inventory with a holding cost, not a story to defend.
4. Liquidity filter: only trade stocks with enough turnover for clean entry and exit.
5. Technology edge: automate monitoring, logs, and alerts before increasing position size.
```

Personal quant system modules:

```text
Data layer:
- Quotes, volume, turnover, amount, limit-up/down state.
- ETF trend and market style.
- Announcements, research headlines, policy/news catalysts.

Signal layer:
- Trend: price above key averages, higher highs, sector confirmation.
- Reversal/grid: ETF falls to predefined buy zone with no structural break.
- Event/catalyst: announcement or order evidence plus same-layer response.
- Heat filter: fast 5%+ spikes are treated as no-chase unless there is second confirmation.

Portfolio layer:
- ETF core: slow beta and grid.
- Stock satellite: only short-term probes at 0.5%-1% first position.
- Permission filter: exclude stocks that the account cannot trade, such as ChiNext or STAR names without account permission.

Execution layer:
- 09:10 plan only.
- 09:40 first decision.
- 10:45 confirmation or lower expectation.
- 14:40 hold/reduce/exit decision.
- Use limit orders; no market chasing.

Risk layer:
- Per pilot trade stop loss around 3%.
- No intraday averaging down.
- No new trade if emotional state is revenge, panic, or missed-move compensation.
- If quote scale or data quality is abnormal, signal is invalid until checked.

Review layer:
- End-of-day trade journal.
- Weekly summary of win rate, average win/loss, rule violations, and missed trades.
- Increase capital only after at least 20 pilot trades with controlled drawdown.
```

Upgrade path:

```text
Phase 1, 2026-05 to 2026-06: manual pilot with 8,000 per stock, max 16,000 total.
Phase 2, 2026-07 to 2026-08: add backtest sheets and daily trade journal; no larger size unless rules are followed.
Phase 3, 2026-09: decide whether the system has enough evidence to increase capital or retrieve outside principal.
Phase 4, after permissions and API access are ready: connect broker data/export, but still keep human confirmation before orders.
```

## 2026-05-19 Short-Term Pilot

This is a familiarity test, not a profit target.

```text
Date: 2026-05-19
Stage: Day 1 short-term pilot
Capital per stock: 8,000
Maximum stocks: 2
Maximum pilot capital: 16,000
Candidates: 600498 Fenghuo Communication, 300054 Dinglong
Expected result if both rise 3%: about 480
Expected result if both rise 5%: about 800
Expected result if both fall 3%: about -480
```

Time windows:

```text
09:10 Read the pre-market plan. Rank candidates and check risk. No order.
09:40 First decision window. Enter only if volume and layer strength confirm.
10:45 Second confirmation window. If the trade does not continue, lower expectations.
14:40 Exit/hold window. Decide whether to take profit, stop loss, or hold overnight.
```

Hard rules:

```text
1. Do not exceed 8,000 per stock on the first pilot day.
2. Do not hold more than two pilot stocks.
3. If a stock opens with a fast 5%+ spike, default to no chase.
4. If loss approaches 3%, accept the test failure and do not average down.
5. Missing the first candle is allowed. Chasing after missing is not allowed.
```

Short-term entry rules:

```text
1. Layer resonance: at least 2-3 stocks in the same layer rise together.
2. Leader confirmation: the leading stock has volume and is not only a one-day event.
3. ETF/index backdrop: related ETF or broad risk appetite is not clearly weakening.
4. Entry style: first position only after pullback, second confirmation, or controlled breakout.
5. Position size: first position 0.5%-1% of total capital; no intraday revenge trade.
```

## Broad A-Share Short-Term Radar

The radar can scan the full A-share market, but the decision layer must stay narrow.

```text
Full A-share scan: about 5,500 stocks
Basic filters: liquidity, tradability, risk flags, intraday strength
Strength board: top 50, used to understand market style
Watch pool: top 10, used for the next 09:40 decision window
Action pool: 1-3 stocks, only eligible for small pilot orders after confirmation
Actual buy: 0-1 new stock per day
```

Position discipline:

```text
1. ETF core remains the main engine.
2. Short-term stocks are only return enhancers, not the main engine.
3. Hold at most 3 short-term individual stocks at the same time.
4. First order stays at 5,000-10,000 unless the system has 20+ reviewed trades.
5. If the action pool is empty, the correct action is no trade.
6. A green action candidate still requires 09:40 volume, layer strength, and order-book confirmation.
```

Action-pool filters:

```text
1. Main-board tradable first, because ChiNext/STAR/Beijing permissions may block execution.
2. Exclude ST, new stocks, illiquid names, and obvious one-word limit-up situations.
3. Prefer stocks with enough turnover, sufficient amount, and volume ratio expansion.
4. Avoid overheated names that already spiked too far intraday.
5. Never buy only because a stock appears in the strength board.
```

## September Decision Gate For Shop Principal

The 700,000 shop principal should not be pulled back only because the market feels exciting. It can be reconsidered around 2026-09 only if the trading system proves it can beat the shop cashflow with controlled drawdown.

Checkpoint date:

```text
Primary checkpoint: 2026-09-30
Secondary early checkpoint: 2026-08-31 only if the account already exceeds the strong threshold and drawdown is controlled.
```

Benchmarks from current trading capital:

| Case by 2026-09-30 | Trading capital target before deciding on shop principal | Market profit required | Decision |
| --- | ---: | ---: | --- |
| Not enough proof | Below 520,000 | Below about 46,000 | Keep shop principal outside; continue with current system |
| Basic proof | 520,000-540,000 | About 46,000-66,000 | Consider taking back only part of the principal |
| Strong proof | 540,000-560,000 | About 66,000-86,000 | Can plan staged retrieval if drawdown is below 8%-10% |
| Very strong proof | Above 560,000 | Above about 86,000 | Can consider retrieving more, but still deploy in batches |

Additional rules:

```text
1. The account must not have a single ETF or stock loss that is being hidden by fresh deposits.
2. Maximum drawdown after June must be controlled below 8%-10%.
3. At least two independent lines must make money, such as ETF core plus one stock satellite theme.
4. If profits mainly come from one lucky stock, do not pull back the full 700,000.
5. If pulled back, deploy the 700,000 in three to six batches, not in one trade.
```

Practical target:

```text
If the account reaches about 540,000-560,000 by 2026-09-30, with no uncontrolled drawdown, the system has enough proof to discuss taking back the shop principal.
If the account is still below 520,000, keep the shop principal outside and use the 3,000/month cashflow as emotional and cashflow stability.
```

## Discipline

The target is 30%, but the method is evidence-first:

```text
Do not buy because the target is high.
Buy only when evidence improves.
Add only when the layer confirms.
Reduce when the story is hot but evidence weakens.
Keep cash when the market does not pay for risk.
```
