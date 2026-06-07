#!/usr/bin/env python3
"""Plan iFind weekly quota usage by trading session.

This script is intentionally read-only. It does not call iFind endpoints.
It converts the weekly quota panel into a practical run list for the local
radar, smart-pick, announcement gate, and review scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "ifind_weekly_budget.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "ifind_usage"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def detect_mode(now: datetime) -> str:
    if now.weekday() >= 5:
        return "weekend"
    hhmm = now.hour * 100 + now.minute
    if hhmm < 925:
        return "premarket"
    if hhmm < 945:
        return "open"
    if 945 <= hhmm <= 1130:
        return "intraday_full"
    if 1130 < hhmm < 1300:
        return "intraday_light"
    if 1300 <= hhmm < 1435:
        return "intraday_full"
    if 1435 <= hhmm <= 1510:
        return "closing"
    return "postclose"


def bucket_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, item in (config.get("quota_buckets") or {}).items():
        quota = float(item.get("quota") or 0)
        used = float(item.get("used") or 0)
        target_pct = float(item.get("target_use_pct") or config.get("policy", {}).get("target_weekly_use_pct") or 75)
        target_used = quota * target_pct / 100 if quota else 0
        remaining_to_target = max(target_used - used, 0)
        reserve = max(quota - target_used, 0)
        rows.append(
            {
                "key": key,
                "label": item.get("label") or key,
                "quota": int(quota),
                "used": int(used),
                "used_pct": round(used / quota * 100, 2) if quota else 0,
                "target_use_pct": target_pct,
                "target_rows_left": int(remaining_to_target),
                "planned_reserve": int(reserve),
                "priority": int(item.get("priority") or 99),
                "stance": item.get("stance") or "",
                "use_for": item.get("use_for") or "",
            }
        )
    return sorted(rows, key=lambda x: (x["priority"], x["key"]))


def build_plan(config: dict[str, Any], mode: str, now: datetime) -> dict[str, Any]:
    modes = config.get("modes") or {}
    mode_config = modes.get(mode) or modes.get("postclose") or {}
    task_commands = config.get("task_commands") or {}
    tasks = []
    for task in mode_config.get("tasks") or []:
        tasks.append(
            {
                "task": task,
                "command": task_commands.get(task, ""),
                "run_policy": "manual_or_scheduler",
            }
        )
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "mode_label": mode_config.get("label") or mode,
        "time_hint": mode_config.get("time_hint") or "",
        "policy": config.get("policy") or {},
        "quota_buckets": bucket_rows(config),
        "tasks": tasks,
        "smart_pick_query_count": len(config.get("smart_pick_queries") or []),
        "notes": [
            "实时行情、日内快照、智能选股和公告查询额度充裕，应该进入日常流程。",
            "历史数据已经使用约35%，后续优先缓存和增量更新。",
            "额度充裕不等于可以扩大交易风险；日亏损软止损触发后，买入候选仍降级为观察。",
        ],
    }


def write_markdown(plan: dict[str, Any], path: Path) -> None:
    lines = [
        "# iFind Weekly Budget Plan",
        "",
        f"生成时间：{plan['generated_at']}",
        f"当前模式：{plan['mode_label']}（{plan['mode']}）",
        f"时段提示：{plan.get('time_hint') or '-'}",
        "",
        "## 本轮应该跑什么",
        "",
        "| 任务 | 命令 |",
        "| --- | --- |",
    ]
    for task in plan.get("tasks") or []:
        lines.append(f"| {task['task']} | `{task.get('command') or '-'}` |")
    lines.extend(
        [
            "",
            "## 周额度预算",
            "",
            "| 优先级 | 接口 | 已用 | 总量 | 已用% | 目标% | 到目标还可用 | 策略 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in plan.get("quota_buckets") or []:
        lines.append(
            f"| {row['priority']} | {row['label']} | {row['used']:,} | {row['quota']:,} | "
            f"{row['used_pct']:.2f}% | {row['target_use_pct']:.0f}% | "
            f"{row['target_rows_left']:,} | {row['stance']} |"
        )
    lines.extend(["", "## 规则", ""])
    for note in plan.get("notes") or []:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def run_tasks(tasks: list[dict[str, Any]], dry_run: bool) -> list[dict[str, Any]]:
    results = []
    for task in tasks:
        command = task.get("command")
        if not command:
            continue
        if dry_run:
            results.append({"task": task["task"], "command": command, "status": "dry_run"})
            continue
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        results.append(
            {
                "task": task["task"],
                "command": command,
                "status": "ok" if completed.returncode == 0 else "failed",
                "returncode": completed.returncode,
                "stdout_tail": (completed.stdout or "")[-1000:],
                "stderr_tail": (completed.stderr or "")[-1000:],
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan iFind weekly quota usage")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--mode", default="auto", choices=["auto", "premarket", "open", "intraday_light", "intraday_full", "closing", "postclose", "weekend"])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--run", action="store_true", help="Run planned task commands after writing the plan")
    parser.add_argument("--dry-run", action="store_true", help="Show task commands without running them")
    args = parser.parse_args()

    now = datetime.now()
    config = read_json(Path(args.config))
    mode = detect_mode(now) if args.mode == "auto" else args.mode
    plan = build_plan(config, mode, now)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    json_path = out_dir / f"{stamp}_ifind_weekly_budget_plan.json"
    md_path = out_dir / f"{stamp}_ifind_weekly_budget_plan.md"

    if args.run or args.dry_run:
        plan["task_results"] = run_tasks(plan["tasks"], dry_run=args.dry_run)

    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(plan, md_path)

    print("=== iFind weekly budget ===")
    print(f"Mode: {plan['mode_label']} ({plan['mode']})")
    print("Tasks:")
    for task in plan.get("tasks") or []:
        print(f"- {task['task']}: {task.get('command') or '-'}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
