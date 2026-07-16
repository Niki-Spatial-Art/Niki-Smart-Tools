# Local A-share Data Gate

The radar now treats market data as a safety dependency rather than a background detail.

## Route

`Tencent Finance quote -> TongdaXin via mootdx daily bars -> Tencent qfq daily bars -> AKShare daily bars`

Run this before the local monitor:

```powershell
.\run_a_stock_radar.ps1
.\run_monitor_local.ps1
```

The snapshot is written to `data/a_stock_radar_snapshot.json`, which stays local and is ignored by Git.

## New-entry gate

New stock entries and tactical-cash transfers are blocked unless all of the following pass:

1. Broad-market scan reaches its configured coverage target.
2. `data/broker_account_snapshots.local.json` is valid, current, and contains account totals plus visible positions.
3. The local A-share data snapshot is within its freshness window and covers every configured position/watchlist code.

Existing holding reviews remain visible when the gate is blocked. The gate prevents new risk; it does not suppress a sell, stop-loss, or hold review.

## Local broker snapshot

Copy `data/broker_account_snapshots.example.json` to `data/broker_account_snapshots.local.json` and enter only manually verified broker values. This repository never connects to a broker or submits an order.

Do not use `portfolio.example.json` for decisions. It exists only to document the schema.
