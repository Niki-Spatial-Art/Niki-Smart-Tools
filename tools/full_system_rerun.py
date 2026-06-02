#!/usr/bin/env python3
"""Run the full local/cloud research stack and optionally email one summary.

The aggregate report covers:

- main radar generation
- action-card export and paper journal summary
- learning intake from curated sources
- public web fetch check for the optional Scrapling connector

It does not place orders and does not scrape private/authenticated pages.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors.public_web_scraper import fetch_public_page, pages_to_json
from emailer import EmailNotifier
from tools.action_audit import build_plan_message


def load_local_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def run_python(args: Iterable[str], env: dict[str, str] | None = None) -> None:
    command = [sys.executable, *args]
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"python step failed ({completed.returncode}): {' '.join(args)}")


def read_text(path: Path, max_chars: int = 9000) -> str:
    if not path.exists():
        return f"Missing: {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n...[truncated {len(text) - max_chars} chars]"
    return text


def summary_from_latest_json(path: Path = ROOT / "reports" / "latest.json") -> str:
    if not path.exists():
        return "latest.json missing"
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [
        f"generated_at: {data.get('generated_at') or data.get('metadata', {}).get('generated_at', '-')}",
        f"radar_results: {len(data.get('results') or [])}",
    ]
    counts = {"green": 0, "yellow": 0, "red": 0}
    for item in data.get("results") or []:
        signal = str(item.get("signal", "")).lower()
        for key in counts:
            if key in signal:
                counts[key] += 1
    lines.append(f"signal_counts: {counts}")

    cards = data.get("action_stack", {}).get("short_term_cards", [])
    lines.append(f"action_cards: {len(cards)}")
    if cards:
        lines.append("top_action_cards:")
        for card in cards[:8]:
            decision_card = card.get("decision_card") or {}
            lines.append(
                "- {code} {name} | {decision} | grade={grade} | capital={capital}".format(
                    code=card.get("code"),
                    name=card.get("name"),
                    decision=card.get("decision"),
                    grade=decision_card.get("grade", "-"),
                    capital=card.get("capital", "-"),
                )
            )
    failures = data.get("failures") or []
    if failures:
        lines.append(f"data_failures: {len(failures)}")
    return "\n".join(lines)


def journal_summary(path: Path = ROOT / "data" / "paper_trade_journal.csv") -> str:
    if not path.exists():
        return "paper_trade_journal.csv missing"
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    closed = 0
    wins = 0
    pnl_total = 0.0
    for row in rows:
        try:
            pnl = float(row.get("pnl") or 0)
        except ValueError:
            pnl = 0.0
        if row.get("actual_exit_price"):
            closed += 1
            pnl_total += pnl
            if pnl > 0:
                wins += 1
    return f"journal_rows: {len(rows)}\nclosed_trades: {closed}\nwins: {wins}\npnl_recorded: {pnl_total:.2f}"


def run_scrapling_check() -> str:
    page = fetch_public_page(
        "https://github.com/D4Vinci/Scrapling",
        backend="requests",
        max_chars=1800,
    )
    output = ROOT / "reports" / "public_web_fetch_scrapling.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(pages_to_json([page]), encoding="utf-8")
    return "\n".join(
        [
            f"backend: {page.backend}",
            f"status_code: {page.status_code}",
            f"robots_allowed: {page.robots_allowed}",
            f"title: {page.title}",
            f"text_sample: {page.text[:500]}",
        ]
    )


def build_html_report(scrapling_text: str) -> str:
    _, action_message = build_plan_message(
        ROOT / "reports" / "latest.json",
        ROOT / "data" / "paper_trade_journal.csv",
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = [
        (
            "运行总览",
            "Full system rerun finished at "
            + now
            + "\n已成功运行：主雷达、行动卡导出/汇总、学习源 intake、Scrapling 公开网页抓取验证。\n"
            + "Dashboard：最新数据已生成；本地服务可用 run_dashboard_local.ps1 打开。",
        ),
        ("系统功能集合", read_text(ROOT / "docs" / "system_feature_collection_2026-06-02.md", 7000)),
        ("主雷达摘要", summary_from_latest_json()),
        ("行动卡审计", action_message),
        ("纸面交易日志摘要", journal_summary()),
        ("Scrapling 公开网页抓取验证", scrapling_text),
        ("学习源报告摘要", read_text(ROOT / "reports" / "learning_intake.md", 8000)),
    ]
    body = []
    for title, content in sections:
        body.append(
            "<h2>{}</h2><pre style='white-space:pre-wrap;font-size:14px;line-height:1.65;"
            "background:#f6f8fa;padding:12px;border-radius:6px'>{}</pre>".format(
                html.escape(title),
                html.escape(content),
            )
        )
    return (
        "<html><body style='font-family:Arial,Microsoft YaHei,sans-serif;color:#222;"
        "max-width:980px;margin:auto'>"
        + "".join(body)
        + "</body></html>"
    )


def send_email(html_content: str) -> bool:
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not sender or not password or not recipient:
        print("aggregate_email_sent=false reason=missing email env")
        return False
    notifier = EmailNotifier(
        sender_email=sender,
        sender_password=password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
    )
    ok = notifier.send_html_alert(
        recipient,
        "Niki Smart Tools 全功能集合报告 - 新功能已重新运行",
        html_content,
    )
    print(f"aggregate_email_sent={ok}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all research/reporting features")
    parser.add_argument("--email", action="store_true", help="send one aggregate email")
    parser.add_argument("--skip-monitor", action="store_true", help="reuse reports/latest.json")
    parser.add_argument("--no-network-learning", action="store_true", help="skip GitHub metadata fetch")
    args = parser.parse_args()

    load_local_env()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)

    if not args.skip_monitor:
        env = dict(os.environ)
        env["MONITOR_SEND_EMAIL"] = "false"
        run_python(["monitor.py"], env=env)

    run_python(
        [
            "tools/action_audit.py",
            "export-plan",
            "--report",
            "reports/latest.json",
            "--journal",
            "data/paper_trade_journal.csv",
        ]
    )
    run_python(["tools/action_audit.py", "summarize", "--journal", "data/paper_trade_journal.csv"])

    learning_args = [
        "tools/learning_intake.py",
        "--sources",
        "examples/learning_sources.json",
        "--output",
        "reports/learning_intake.md",
    ]
    if args.no_network_learning:
        learning_args.append("--no-network")
    run_python(learning_args)

    scrapling_text = run_scrapling_check()
    html_content = build_html_report(scrapling_text)
    (ROOT / "reports" / "full_system_rerun.html").write_text(html_content, encoding="utf-8")
    print("full_system_report=reports/full_system_rerun.html")

    if args.email:
        return 0 if send_email(html_content) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
