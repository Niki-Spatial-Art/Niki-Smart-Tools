---
name: mason-trading-knowledge
description: Personal Mason/梅森/梅家圈 A-share trading knowledge-base workflow for turning a local folder of reports, PDFs, Excel sheets, and circle notes into theme logic, watchlist context, buy/sell/hold/reduce/clear action cards, position discipline, and post-close review. Use when the user mentions 梅森, 梅家圈, 梅花庄, 双跌买点, 顺大势逆小势, 盘中动作卡, 交易知识库, or asks how a theme/stock/ETF fits their account.
---

# Mason Trading Knowledge

Use this skill as a personal research and discipline layer, not as investment advice or automated trading. It helps translate the user's local Mason/梅家圈 materials into practical A-share/ETF decision support.

## Safety Boundary

- Never place orders or operate broker software.
- Never promise profits or say a trade is guaranteed.
- Do not upload or quote long copyrighted source documents.
- Treat source materials as evidence and style references, then adapt them to the user's current portfolio, cash, risk tolerance, and A-share rules.
- If data is stale, user-reported, or from screenshots, say so.

## Source Layout

Default local source folder:

```text
D:\梅森
```

Default workbench index:

```text
data\mason_library\mason_library_index.json
```

If the index is missing or stale, run:

```powershell
python tools/index_mason_library.py --source "D:\梅森"
```

## Core Method

Answer in this order during market hours:

1. Identify the theme: macro/style, AI compute, CPO/optical communication, PCB/ABF, semiconductor/materials, small metals, energy/chemical, robot/AI application, or other.
2. Check whether the user's account already has exposure to that theme.
3. Translate the Mason logic into a decision card, not a story.
4. Prefer "wait/no add" unless there is a real setup: big trend intact + short-term pullback + account has risk room.
5. Use small position sizing for new positions. Do not let FOMO turn a clean adjustment into overtrading.

## Output Format

For intraday questions, output a compact action card:

```text
动作：买 / 不买 / 持有 / 减 / 清
置信度：低 / 中 / 高
触发：价格或盘面条件
失效：跌破/放量转弱/主题证伪/账户风险超限
仓位：股数、份额或金额上限
风险：T+1、同方向拥挤、节假日、回撤金额
下次检查：时间或价格
```

For learning/research questions, output:

- Theme thesis
- Key evidence from local index
- A-share mapping
- Suitable products for this user's account
- Avoid/chase-risk list
- Action-card rule that can be reused

## User-Specific Rules

- The user often cannot buy ChiNext `300xxx`; filter direct `300` stocks unless they say access changed.
- Be cautious with STAR `688xxx` direct stocks; ETFs are usually cleaner unless the user confirms access and risk tolerance.
- The user tends to FOMO after group messages. Anchor on: "not every good stock is suitable for this account today."
- Do not suggest transferring bank cash into the brokerage account to chase.
- Repeated same-theme exposure counts as one risk bucket. Example: `515050` + `600487` + `588000` already creates technology/communication beta.

## Mason Heuristics To Apply

- 顺大势、逆小势: only buy when market/sector trend is up but short-term price pulls back.
- 双跌买点: market and target both dip, but trend is not broken.
- 均线引力: when price is far above moving averages, prefer holding existing positions, not chasing.
- 圈内不缺机会: missing one ticket is acceptable; losing discipline is the bigger cost.
- 赚自己认知内的钱: prefer products and themes the user's account can actually hold through volatility.

## References

Read `references/action_card_rules.md` when generating trade cards.
Read `references/theme_taxonomy.md` when mapping a document/theme to A-share sectors and likely ETFs/stocks.
