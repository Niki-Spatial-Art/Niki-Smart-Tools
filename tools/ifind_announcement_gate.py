#!/usr/bin/env python3
"""iFind announcement/report risk gate for holdings and watchlist.

This is a read-only evidence check. It marks names that deserve manual review
before any new buy, especially after large moves or risk announcements.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.ifind_http import IFindHTTPClient, IFindHTTPError


DEFAULT_OUTPUT_DIR = ROOT / "reports" / "announcement_checks"
RISK_KEYWORDS = [
    "担保",
    "质押",
    "减持",
    "异常波动",
    "诉讼",
    "处罚",
    "立案",
    "问询",
    "亏损",
    "退市",
    "ST",
    "解禁",
    "业绩预告",
    "更正",
]


def load_local_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ifind_code(code: str) -> str:
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{'SH' if code[:1] in {'5', '6', '9'} else 'SZ'}"


def plain_code(code: str) -> str:
    return str(code).split(".", 1)[0]


def read_portfolio(path: Path) -> tuple[list[str], dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    codes: list[str] = []
    names: dict[str, str] = {}
    for item in payload.get("positions") or []:
        code = str(item.get("code") or "").strip()
        if code:
            codes.append(code)
            names[code] = str(item.get("name") or code)
    for code in payload.get("watchlist") or []:
        code = str(code).strip()
        if code and code not in codes:
            codes.append(code)
    return codes, names


def parse_report_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in payload.get("tables") or []:
        thscode = plain_code(str(table.get("thscode") or ""))
        raw = table.get("table") or {}
        if not isinstance(raw, dict):
            continue
        count = max((len(v) for v in raw.values() if isinstance(v, list)), default=0)
        for idx in range(count):
            row = {"code": thscode}
            for key, values in raw.items():
                if isinstance(values, list):
                    row[key] = values[idx] if idx < len(values) else None
                else:
                    row[key] = values
            rows.append(row)
    return rows


def title_text(row: dict[str, Any]) -> str:
    parts = []
    for key in ("reportTitle", "title", "公告标题", "secName", "证券简称"):
        value = row.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run iFind announcement/report risk gate")
    parser.add_argument("--portfolio", default=str(ROOT / "portfolio.local.json"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--codes", default="", help="Comma-separated 6-digit codes; default portfolio positions + watchlist")
    args = parser.parse_args()

    load_local_env()
    if args.codes:
        codes = [code.strip() for code in args.codes.split(",") if code.strip()]
        names = {}
    else:
        codes, names = read_portfolio(Path(args.portfolio))

    end = datetime.now()
    start = end - timedelta(days=args.days)
    client = IFindHTTPClient()
    ifind_codes = [ifind_code(code) for code in codes]
    rows: list[dict[str, Any]] = []
    error = ""
    try:
        payload = client.report_query(
            ifind_codes,
            begin_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        rows = parse_report_rows(payload)
    except IFindHTTPError as exc:
        error = str(exc)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    flagged = []
    for row in rows:
        text = title_text(row)
        hits = [kw for kw in RISK_KEYWORDS if kw.lower() in text.lower()]
        if hits:
            row["risk_keywords"] = hits
            row["name_hint"] = names.get(str(row.get("code") or ""))
            flagged.append(row)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "iFind report_query",
        "days": args.days,
        "codes": codes,
        "row_count": len(rows),
        "flagged_count": len(flagged),
        "error": error,
        "risk_keywords": RISK_KEYWORDS,
        "warning": "Flagged rows require manual review before any new buy. This script does not trade.",
        "flagged": flagged,
        "rows_sample": rows[:100],
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = out_dir / f"{stamp}_ifind_announcement_gate.json"
    md_path = out_dir / f"{stamp}_ifind_announcement_gate.md"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# iFind Announcement Gate",
        "",
        f"生成时间：{output['generated_at']}",
        f"覆盖标的：{len(codes)}，记录：{output['row_count']}，风险命中：{output['flagged_count']}",
        "",
    ]
    if error:
        lines.append(f"错误：{error}")
        lines.append("")
    lines.extend(
        [
            "说明：命中项只表示买入前必须人工复核，不代表一定卖出或不能持有。",
            "",
            "| 代码 | 名称 | 命中词 | 标题 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in flagged[:80]:
        title = title_text(row).replace("|", " ")
        lines.append(
            f"| {row.get('code') or '-'} | {row.get('name_hint') or row.get('secName') or '-'} | "
            f"{','.join(row.get('risk_keywords') or [])} | {title} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=== iFind announcement gate ===")
    print(f"Rows: {output['row_count']}, flagged: {output['flagged_count']}")
    if error:
        print(f"Error: {error}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    return 0 if not error else 1


if __name__ == "__main__":
    raise SystemExit(main())
