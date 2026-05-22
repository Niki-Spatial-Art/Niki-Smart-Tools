"""Action-card paper trading journal helpers.

This intentionally stays small: export today's action cards into a CSV journal,
then summarize closed paper/real trades after the user fills execution details.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


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
                "t_plus_one_plan": "A股T+1：若真实买入，下一交易日按止盈/止损计划处理；当天不卖。",
            }
        )
    return rows


def export_plan(report: Path, journal: Path) -> None:
    existing = read_journal(journal)
    seen = {row.get("plan_id") for row in existing}
    new_rows = [row for row in cards_from_report(report) if row.get("plan_id") not in seen]
    write_journal(journal, [*existing, *new_rows])
    print(f"exported={len(new_rows)} journal={journal}")


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
    parser = argparse.ArgumentParser(description="Action-card journal helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    export_cmd = sub.add_parser("export-plan")
    export_cmd.add_argument("--report", default="reports/latest.json")
    export_cmd.add_argument("--journal", default="data/paper_trade_journal.csv")

    summary_cmd = sub.add_parser("summarize")
    summary_cmd.add_argument("--journal", default="data/paper_trade_journal.csv")

    args = parser.parse_args()
    if args.command == "export-plan":
        export_plan(Path(args.report), Path(args.journal))
    elif args.command == "summarize":
        summarize(Path(args.journal))


if __name__ == "__main__":
    main()

