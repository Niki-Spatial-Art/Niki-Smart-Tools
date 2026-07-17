# Niki Investment Decision Workbench

The local dashboard is a decision-discipline tool, not an automated trading
system. Its default order is:

1. Confirm the latest broker snapshot and available shares.
2. Manage risk and profits in existing holdings.
3. Read the market environment.
4. Use news, announcements, fund flow, and leaderboard data after close to
   maintain an observation list.

Options are simulation/research only. Xingyao is a local optional research
source. iFind is off by default. Neither is part of the default dashboard
refresh or the GitHub Actions workflow.

## Local Start

```powershell
./run_investment_workbench.ps1
```

Open `http://127.0.0.1:8501/`. The dashboard never connects to a broker and
does not place orders.

## A-share Data Route

The public route is Tencent Finance quote -> TongdaXin via mootdx -> Tencent
Finance qfq K-line -> AKShare. `requirements-a-stock.txt` pins the optional
full-route dependencies. Set `A_STOCK_PYTHON` to a prepared Python executable
when the local environment already contains them:

```powershell
$env:A_STOCK_PYTHON = 'C:\path\to\python.exe'
./run_investment_workbench.ps1
```

If a source is unavailable, the dashboard must downgrade new entries to
observation; it must not block review of existing positions.
