# Workflows

## End-to-End Quant Radar Workflow

```text
1. Load configuration
2. Fetch and normalize quotes
3. Run ETF/A-share/option radar
4. Apply risk gates and portfolio constraints
5. Generate action cards
6. Archive Markdown/JSON reports
7. Send email or render local dashboard
8. Export action cards to the paper journal
9. Human reviews actual execution and outcome
```

## Research Director SOP

External articles, model ideas, and trading intuition should enter the system
through a research-director workflow:

```text
1. User states the market hypothesis in one sentence
2. AI turns it into a computable factor or theme rule
3. AI writes or updates the smallest validation script/report
4. System checks sample size, T+1/T+2/T+5 outcome, drawdown, and redundancy
5. Only validated ideas can influence action-card wording
6. Human decides whether to trade and reports execution back to the journal
```

The AI may implement, test, summarize, and audit. It must not invent alpha,
promise returns, or place live orders.

## Offline Demo

Run:

```powershell
python workflows/demo_quant_research.py
```

The demo does not require network access or secrets. It uses a small sample report under `examples/`, writes the journal to a temporary directory, and prints a morning review message.

## Production-Like Local Workflow

```powershell
python monitor.py
python tools/action_audit.py export-plan --report reports/latest.json --journal data/paper_trade_journal.csv
python tools/action_audit.py summarize --journal data/paper_trade_journal.csv
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_dashboard_local.ps1
```

## Windows Scheduled Workflow

Install local action-card audit at 09:00:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_action_audit_0900_task.ps1
```

The task exports paper plans, summarizes the journal, and attempts notification. It should not place orders.
