"""Action-card paper trading journal helpers.

This intentionally stays small: export today's action cards into a CSV journal,
then summarize closed paper/real trades after the user fills execution details.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emailer import EmailNotifier


FIELDS = [
    "plan_id",
    "date",
    "generated_at",
    "code",
    "name",
    "decision",
    "grade",
    "window",
    "planned_capital",
    "planned_shares",
    "entry_low",
    "entry_high",
    "take_profit_1",
    "take_profit_2",
    "stop_loss",
    "risk_gate",
    "reason",
    "t_plus_one_plan",
    "actual_entry_time",
    "actual_entry_price",
    "actual_shares",
    "actual_exit_time",
    "actual_exit_price",
    "pnl",
    "pnl_pct",
    "outcome",
    "review",
]


def load_local_env(path: str = ".env") -> None:
    """Load KEY=VALUE settings for local Windows scheduled runs."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _plan_id(generated_at: str, code: str, decision: str) -> str:
    raw = f"{generated_at}|{code}|{decision}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def read_journal(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_journal(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def cards_from_report(path: Path) -> List[Dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    generated_at = (
        payload.get("metadata", {}).get("generated_at")
        or payload.get("action_stack", {}).get("generated_at")
        or payload.get("generated_at")
        or ""
    )
    cards = payload.get("action_stack", {}).get("short_term_cards", [])
    rows = []
    for card in cards:
        decision_card = card.get("decision_card") or {}
        take_profit = decision_card.get("take_profit") or []
        date = generated_at[:10] or datetime.now().strftime("%Y-%m-%d")
        code = _fmt(card.get("code"))
        decision = _fmt(card.get("decision"))
        rows.append(
            {
                "plan_id": _plan_id(generated_at, code, decision),
                "date": date,
                "generated_at": generated_at,
                "code": code,
                "name": _fmt(card.get("name")),
                "decision": decision,
                "grade": _fmt(decision_card.get("grade")),
                "window": _fmt(decision_card.get("window")),
                "planned_capital": _fmt(card.get("capital")),
                "planned_shares": _fmt(card.get("shares")),
                "entry_low": _fmt(card.get("entry_low")),
                "entry_high": _fmt(card.get("entry_high")),
                "take_profit_1": _fmt(card.get("take_profit_1") or (take_profit[0] if take_profit else "")),
                "take_profit_2": _fmt(card.get("take_profit_2") or (take_profit[1] if len(take_profit) > 1 else "")),
                "stop_loss": _fmt(card.get("stop_loss")),
                "risk_gate": _fmt((card.get("risk_gate") or {}).get("level")),
                "reason": _fmt(card.get("reason") or card.get("action")),
                "t_plus_one_plan": "A-share T+1: if a real buy is made, handle it on the next trading day according to the take-profit/stop-loss plan; do not sell same day.",
            }
        )
    return rows


def export_plan(report: Path, journal: Path) -> int:
    existing = read_journal(journal)
    seen = {row.get("plan_id") for row in existing}
    new_rows = [row for row in cards_from_report(report) if row.get("plan_id") not in seen]
    write_journal(journal, [*existing, *new_rows])
    print(f"exported={len(new_rows)} journal={journal}")
    return len(new_rows)


def latest_plan_rows(report: Path, journal: Path) -> List[Dict[str, str]]:
    cards = cards_from_report(report)
    latest_ids = {row.get("plan_id") for row in cards}
    if not latest_ids:
        return []
    return [row for row in read_journal(journal) if row.get("plan_id") in latest_ids]


def build_plan_message(report: Path, journal: Path) -> tuple[str, str]:
    rows = latest_plan_rows(report, journal)
    generated_at = ""
    new_entry_gate = {}
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        generated_at = (
            payload.get("metadata", {}).get("generated_at")
            or payload.get("action_stack", {}).get("generated_at")
            or payload.get("generated_at")
            or ""
        )
        new_entry_gate = (payload.get("action_stack") or {}).get("new_entry_gate") or {}
    except Exception:
        generated_at = ""

    lines = [
        "Intraday Action Card Scan",
        f"report={report}",
        f"journal={journal}",
        f"generated_at={generated_at or '-'}",
        "",
        "Morning discipline:",
        "1. Paper log first; no auto order.",
        "2. Before any real buy, write why buy, how much, and next trading-day exit plan.",
        "3. A-share T+1: same-day sell is unavailable for new buys.",
    ]
    gate_label = "OPEN: manual review allowed" if not new_entry_gate.get("blocked") else "CLOSED: no new entry"
    lines.extend([
        "",
        f"New-entry gate: {gate_label}",
        f"Gate reason: {new_entry_gate.get('reason') or '-'}",
    ])

    if not rows:
        lines.extend(["", "No action cards were found in the latest report.", "Keep the morning report as observation only; do not force a trade."])
        return "Niki intraday action cards - no new entry", "\n".join(lines)

    lines.append("")
    lines.append("Latest action cards:")
    for row in rows:
        lines.extend(
            [
                "",
                f"- {row.get('code')} {row.get('name')} | {row.get('decision')} | grade={row.get('grade') or '-'}",
                f"  planned_capital={row.get('planned_capital') or '-'} planned_shares={row.get('planned_shares') or '-'}",
                f"  entry={row.get('entry_low') or '-'}-{row.get('entry_high') or '-'} tp={row.get('take_profit_1') or '-'}/{row.get('take_profit_2') or '-'} stop={row.get('stop_loss') or '-'}",
                f"  reason={row.get('reason') or '-'}",
            ]
        )
    return "Niki intraday action cards - manual review", "\n".join(lines)


def send_plan_email(report: Path, journal: Path) -> bool:
    load_local_env()
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not sender or not password or not recipient:
        print("email_skipped=missing SENDER_EMAIL/SENDER_PASSWORD/RECIPIENT_EMAIL")
        return False
    placeholders = ("your_", "example", "xxx", "填入", "替换")
    if any(token in sender.lower() for token in placeholders) or any(token in recipient.lower() for token in placeholders):
        print("email_skipped=placeholder email config in .env")
        print("next_step=fill local .env with real SENDER_EMAIL, SENDER_PASSWORD authorization code, and RECIPIENT_EMAIL")
        return False
    if any(token in password.lower() for token in placeholders):
        print("email_skipped=placeholder email password in .env")
        print("next_step=use the QQ mail SMTP authorization code, not the login password")
        return False

    subject, message = build_plan_message(report, journal)
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2>Niki 盘中动作卡扫描</h2>
        <pre style="font-size: 14px; line-height: 1.65; white-space: pre-wrap;">{html.escape(message)}</pre>
      </body>
    </html>
    """
    notifier = EmailNotifier(
        sender_email=sender,
        sender_password=password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
    )
    ok = notifier.send_html_alert(recipient, subject, html_content)
    print(f"email_sent={ok}")
    return ok


def summarize(journal: Path) -> None:
    rows = read_journal(journal)
    closed = []
    for row in rows:
        try:
            entry = float(row.get("actual_entry_price") or 0)
            exit_ = float(row.get("actual_exit_price") or 0)
            shares = float(row.get("actual_shares") or 0)
        except ValueError:
            continue
        if entry > 0 and exit_ > 0 and shares > 0:
            pnl = (exit_ - entry) * shares
            row["pnl"] = f"{pnl:.2f}"
            row["pnl_pct"] = f"{(exit_ / entry - 1) * 100:.2f}"
            closed.append(row)

    wins = [row for row in closed if float(row["pnl"]) > 0]
    total_pnl = sum(float(row["pnl"]) for row in closed)
    win_rate = (len(wins) / len(closed) * 100) if closed else 0
    print(f"closed_trades={len(closed)} wins={len(wins)} win_rate={win_rate:.1f}% pnl={total_pnl:.2f}")
    if not closed:
        print("next_step=fill actual_entry_price, actual_shares, actual_exit_price after T+1 exits")


def main() -> None:
    load_local_env()
    parser = argparse.ArgumentParser(description="Action-card journal helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    export_cmd = sub.add_parser("export-plan")
    export_cmd.add_argument("--report", default="reports/latest.json")
    export_cmd.add_argument("--journal", default="data/paper_trade_journal.csv")

    summary_cmd = sub.add_parser("summarize")
    summary_cmd.add_argument("--journal", default="data/paper_trade_journal.csv")

    notify_cmd = sub.add_parser("notify-plan")
    notify_cmd.add_argument("--report", default="reports/latest.json")
    notify_cmd.add_argument("--journal", default="data/paper_trade_journal.csv")

    args = parser.parse_args()
    if args.command == "export-plan":
        export_plan(Path(args.report), Path(args.journal))
    elif args.command == "summarize":
        summarize(Path(args.journal))
    elif args.command == "notify-plan":
        ok = send_plan_email(Path(args.report), Path(args.journal))
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
