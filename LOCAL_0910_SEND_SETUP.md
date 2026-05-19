# Local 09:10 Send Setup

GitHub Actions schedule is not a precise alarm clock. It may run late when GitHub is busy, even when the cron setting is correct.

For the 09:10 pre-market email, use a local Windows scheduled task as the primary trigger, and keep GitHub Actions as the cloud backup.

## One-time setup

Run this in PowerShell from the repository folder:

```powershell
cd "C:\Users\Niki_Spatial\Documents\Codex\2026-05-12\codex-github-api-github-workflows-monitor"
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_windows_0910_task.ps1
```

This installs a Windows task named:

```text
ETF Strategy Monitor 0910
```

It runs Monday-Friday at 09:10 Beijing time.

## Test manually

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_monitor_local.ps1
```

Logs are saved under:

```text
logs\
```

## Notes

The local task needs:

```text
1. The computer is on or wakes in time.
2. Network is available.
3. .env contains the email and AI settings.
4. Python dependencies are installed.
```

GitHub Actions remains useful as a backup, but the local task is the more reliable 09:10 trigger.
