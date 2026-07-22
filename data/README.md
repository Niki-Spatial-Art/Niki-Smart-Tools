# Local Data Directory

This directory is intentionally ignored by git except for this note.

Keep broker screenshots, account snapshots, iFind probes, generated dashboards,
paper journals, logs, and other private runtime files here. Do not commit live
account data, access-token-bearing API responses, or local machine paths.

Two local-only files complete the research loop:

- `research_evidence.local.json`: source-backed candidate cards. A candidate
  remains observation-only until its data and logic checks are both complete.
- `trade_attributions.local.csv`: post-trade review keyed by `trade_time` and
  `code`. It separates market state, selection, sizing, execution, and result.

Copy the matching files from `examples/` as a starting point. Neither file is
sent to GitHub Actions, email, or external services.
