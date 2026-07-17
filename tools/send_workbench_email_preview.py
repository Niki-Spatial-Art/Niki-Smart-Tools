#!/usr/bin/env python3
"""Send a manual, public-market email preview for the investment workbench."""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a_stock_market_data import snapshot
from emailer import EmailNotifier


WATCH_CODES = ["510300", "512100", "512880", "588000", "518880"]


def fmt_price(value: object) -> str:
    try:
        return f"{float(value):.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "-"


def fmt_pct(value: object) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "-"


def build_html(payload: dict) -> str:
    generated_at = str(payload.get("generated_at") or "-")
    status = payload.get("status") or {}
    rows = []
    for code in WATCH_CODES:
        quote = (payload.get("quotes") or {}).get(code) or {}
        change = quote.get("change_pct")
        color = "#b42318" if isinstance(change, (int, float)) and change < 0 else "#18794e"
        rows.append(
            "<tr>"
            f"<td>{html.escape(code)}</td>"
            f"<td>{html.escape(str(quote.get('name') or '-'))}</td>"
            f"<td>{html.escape(fmt_price(quote.get('price')))}</td>"
            f"<td style=\"color:{color};font-weight:700\">{html.escape(fmt_pct(change))}</td>"
            f"<td>{html.escape(str(quote.get('quote_time') or '-'))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f4f6f8;color:#172033;font:14px Arial,'Microsoft YaHei',sans-serif;line-height:1.55">
  <main style="max-width:720px;margin:0 auto;padding:24px">
    <section style="background:#fff;border:1px solid #d8dee8;border-radius:8px;padding:22px">
      <h1 style="margin:0;font-size:24px">Niki 投资决策工作台</h1>
      <p style="color:#5d6b82">邮件预览 | {html.escape(generated_at)}</p>
      <div style="background:#eef5ff;border:1px solid #bdd3f4;padding:12px;border-radius:6px">
        <strong>使用顺序：</strong>先核对券商 App 的账户与可卖份额，再处理已有持仓；市场快照只用于判断环境，不构成买入指令。
      </div>
      <h2 style="font-size:17px;margin-top:22px">公共市场快照</h2>
      <p style="color:#5d6b82">报价 {status.get('valid_quote_count', 0)}/{len(WATCH_CODES)}；日线 {status.get('valid_history_count', 0)}/{len(WATCH_CODES)}。数据路由：腾讯实时行情 -> 通达信日线 -> 腾讯前复权 K 线 -> AKShare。</p>
      <table style="width:100%;border-collapse:collapse;margin-top:12px">
        <thead><tr style="background:#f7f9fc"><th style="text-align:left;padding:8px">代码</th><th style="text-align:left;padding:8px">标的</th><th style="text-align:right;padding:8px">价格</th><th style="text-align:right;padding:8px">涨跌幅</th><th style="text-align:right;padding:8px">报价时间</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p style="margin-top:20px;color:#5d6b82;font-size:12px">本邮件不包含账户、持仓或个人配置；不连接券商、不自动下单、不承诺收益。</p>
    </section>
  </main>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a manual workbench email preview")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate the preview without SMTP")
    args = parser.parse_args()

    payload = snapshot(WATCH_CODES, bars=5)
    email_html = build_html(payload)
    if args.dry_run:
        print(f"dry_run=OK quotes={(payload.get('status') or {}).get('valid_quote_count', 0)}/{len(WATCH_CODES)} html_bytes={len(email_html.encode('utf-8'))}")
        return 0

    required = {name: os.getenv(name, "").strip() for name in ("SENDER_EMAIL", "SENDER_PASSWORD", "RECIPIENT_EMAIL")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit("Missing required email configuration: " + ", ".join(missing))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    notifier = EmailNotifier(
        sender_email=required["SENDER_EMAIL"],
        sender_password=required["SENDER_PASSWORD"],
        smtp_server=(os.getenv("SMTP_SERVER") or "smtp.qq.com").strip(),
        smtp_port=int((os.getenv("SMTP_PORT") or "587").strip()),
    )
    sent = notifier.send_html_alert(required["RECIPIENT_EMAIL"], f"Niki 决策工作台 | 邮件预览 | {now}", email_html)
    if not sent:
        raise SystemExit("SMTP did not accept the email preview")
    print("email_preview=sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
