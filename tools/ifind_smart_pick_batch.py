#!/usr/bin/env python3
"""Run a daily batch of iFind smart-pick queries.

The output is a candidate evidence pool, not a buy list. Action cards must
still pass price, backtest, announcement, and risk gates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.ifind_http import IFindHTTPClient, IFindHTTPError


DEFAULT_CONFIG = ROOT / "data" / "ifind_weekly_budget.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "smart_pick"


def load_local_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows_from_table(table: dict[str, Any]) -> list[dict[str, Any]]:
    columns = {key: value for key, value in table.items() if isinstance(value, list)}
    if not columns:
        return []
    count = max(len(values) for values in columns.values())
    rows = []
    for idx in range(count):
        row = {}
        for key, values in columns.items():
            row[key] = values[idx] if idx < len(values) else None
        rows.append(row)
    return rows


def extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    response = ((payload.get("data") or {}).get("response") or {}) if isinstance(payload.get("data"), dict) else {}
    for item in response.get("tables") or payload.get("tables") or []:
        if not isinstance(item, dict):
            continue
        table = item.get("table")
        if isinstance(table, dict):
            rows.extend(rows_from_table(table))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run iFind smart-pick query batch")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--query", action="append", default=[], help="Extra query; can be repeated")
    args = parser.parse_args()

    load_local_env()
    config = read_json(Path(args.config))
    queries = list(config.get("smart_pick_queries") or [])
    queries.extend(args.query)
    queries = queries[: max(args.limit, 0)]

    client = IFindHTTPClient()
    results = []
    unique_rows: dict[str, dict[str, Any]] = {}
    for idx, query in enumerate(queries, start=1):
        item: dict[str, Any] = {
            "idx": idx,
            "query": query,
            "ok": False,
            "rows": [],
        }
        try:
            payload = client.smart_stock_picking(query)
            rows = extract_rows(payload)
            item["ok"] = True
            item["row_count"] = len(rows)
            item["rows"] = rows[:50]
            for row in rows:
                key = str(row.get("股票代码") or row.get("thscode") or row.get("代码") or row.get("证券代码") or row)
                unique_rows.setdefault(key, row)
        except IFindHTTPError as exc:
            item["error"] = str(exc)
        except Exception as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        results.append(item)
        if args.sleep > 0:
            time.sleep(args.sleep)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "iFind smart_stock_picking",
        "query_count": len(queries),
        "ok_count": sum(1 for item in results if item.get("ok")),
        "unique_row_count": len(unique_rows),
        "warning": "This is a candidate evidence pool only, not a buy signal.",
        "results": results,
        "unique_rows": list(unique_rows.values()),
    }
    json_path = out_dir / f"{stamp}_ifind_smart_pick_batch.json"
    md_path = out_dir / f"{stamp}_ifind_smart_pick_batch.md"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# iFind Smart Pick Batch",
        "",
        f"生成时间：{output['generated_at']}",
        f"问句数：{output['query_count']}，成功：{output['ok_count']}，候选去重：{output['unique_row_count']}",
        "",
        "说明：这是候选证据池，不是买入清单。买入仍必须过价格、回测、公告、风控闸门。",
        "",
        "| # | 问句 | 状态 | 行数 |",
        "| ---: | --- | --- | ---: |",
    ]
    for item in results:
        status = "OK" if item.get("ok") else "FAILED"
        lines.append(f"| {item['idx']} | {item['query']} | {status} | {item.get('row_count', 0)} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=== iFind smart pick batch ===")
    print(f"Queries: {output['query_count']}, OK: {output['ok_count']}, unique rows: {output['unique_row_count']}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    return 0 if output["ok_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
