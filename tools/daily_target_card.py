#!/usr/bin/env python3
"""Create a local daily target card from risk rules and trade-review samples.

The card is a planning and review artifact. It does not promise returns and it
does not place orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def yuan(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "-"


def portfolio_path() -> Path:
    configured = os.getenv("PORTFOLIO_FILE")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    local = ROOT / "portfolio.local.json"
    return local if local.exists() else ROOT / "portfolio.json"


def short_term_pilot(portfolio: dict[str, Any]) -> dict[str, Any]:
    return ((portfolio.get("capital_plan") or {}).get("short_term_pilot") or {})


def latest_action_cards(report_path: Path) -> list[dict[str, Any]]:
    data = load_json(report_path)
    return ((data.get("action_stack") or {}).get("short_term_cards") or [])


def summarize_review_samples(rows: list[dict[str, str]]) -> dict[str, Any]:
    tags = Counter(row.get("problem_tag") or "untagged" for row in rows)
    open_rows = [row for row in rows if row.get("sample_type") == "open"]
    closed_rows = [row for row in rows if row.get("sample_type") == "closed"]
    pnl_total = 0.0
    wins = 0
    closed_count = 0
    for row in closed_rows:
        raw = (row.get("pnl") or "0").replace(",", "")
        try:
            pnl = float(raw)
        except ValueError:
            continue
        closed_count += 1
        pnl_total += pnl
        if pnl > 0:
            wins += 1
    return {
        "tags": tags,
        "open_rows": open_rows,
        "closed_count": closed_count,
        "wins": wins,
        "pnl_total": pnl_total,
        "win_rate": (wins / closed_count * 100) if closed_count else None,
    }


def is_do_card(card: dict[str, Any]) -> bool:
    decision = str(card.get("decision") or "")
    return decision in {"做", "买", "buy", "BUY"}


def card_for_action(card: dict[str, Any]) -> str:
    decision_card = card.get("decision_card") or {}
    risk_gate = card.get("risk_gate") or {}
    return (
        f"| {card.get('code', '-')} {card.get('name', '-')} "
        f"| {card.get('decision', '-')} "
        f"| {decision_card.get('grade', '-')} "
        f"| {yuan(card.get('capital'))} / {card.get('shares', '-')}股 "
        f"| {card.get('entry_low', '-')}-{card.get('entry_high', '-')} "
        f"| {card.get('stop_loss', '-')} "
        f"| {risk_gate.get('level', '-')} |"
    )


def build_target_card(
    portfolio: dict[str, Any],
    report_path: Path,
    review_rows: list[dict[str, str]],
    monthly_target: float,
    trading_days: int,
) -> str:
    pilot = short_term_pilot(portfolio)
    review = summarize_review_samples(review_rows)
    daily_target = monthly_target / max(trading_days, 1)
    short_bucket = float(pilot.get("max_total_capital") or 100000)
    default_capital = float(pilot.get("capital_per_stock") or 20000)
    strong_capital = float(pilot.get("strong_signal_capital_per_stock") or 30000)
    stop_loss_pct = float(pilot.get("stop_loss_pct") or 0.03)
    soft_stop = float(pilot.get("daily_loss_soft_stop") or -1200)
    hard_stop = float(pilot.get("daily_loss_hard_stop") or -2000)
    no_chase = float(pilot.get("no_chase_pct") or 5.2)

    required_bucket_return = daily_target / short_bucket * 100 if short_bucket else 0
    required_default_trade_return = daily_target / default_capital * 100 if default_capital else 0
    max_single_loss = -default_capital * stop_loss_pct
    action_cards = latest_action_cards(report_path)
    do_cards = [card for card in action_cards if is_do_card(card)]
    watch_cards = action_cards[:6]
    top_tags = ", ".join(f"{tag}={count}" for tag, count in review["tags"].most_common(5)) or "-"
    open_names = ", ".join(
        f"{row.get('code')} {row.get('name')}({row.get('problem_tag')})"
        for row in review["open_rows"][:8]
    ) or "-"

    realism = "可作为强行情压力测试，但不能当成每日任务"
    if required_bucket_return > 5:
        realism = "非常激进：除非出现明确主线共振，否则不应强行追求"
    elif required_bucket_return <= 3:
        realism = "激进但可用作强信号日参考"

    lines = [
        "# 每日目标卡",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"组合文件：`{portfolio_path().name}`",
        f"雷达报告：`{report_path.as_posix()}`",
        "",
        "## 月目标压力测试",
        "",
        "| 项目 | 数值 |",
        "| --- | ---: |",
        f"| 月度股票收益目标 | {yuan(monthly_target)} 元 |",
        f"| 按 {trading_days} 个交易日折算 | {yuan(daily_target)} 元/日 |",
        f"| 短线桶参考 | {yuan(short_bucket)} 元 |",
        f"| 每日需短线桶收益率 | {required_bucket_return:.2f}% |",
        f"| 单只默认仓 {yuan(default_capital)} 元需收益率 | {required_default_trade_return:.2f}% |",
        f"| B级单只默认仓 | {yuan(default_capital)} 元 |",
        f"| A级强确认单只 | {yuan(strong_capital)} 元 |",
        "",
        f"结论：{realism}。目标只用于拆解压力，不用于强迫交易。",
        "",
        "## 今日风控闸门",
        "",
        "| 闸门 | 数值 | 动作 |",
        "| --- | ---: | --- |",
        f"| 软熔断 | {yuan(soft_stop)} 元 | 接近后只允许减仓或极小试错 |",
        f"| 硬熔断 | {yuan(hard_stop)} 元 | 达到后停止新开仓 |",
        f"| 单笔止损参考 | {pct(stop_loss_pct * 100)} | 不补仓摊低 |",
        f"| 单笔默认最大亏损 | {yuan(max_single_loss)} 元 | 买入前先承认这个损失 |",
        f"| 追高禁区 | 涨幅 >= {no_chase:.1f}% | 默认不追，除非次级确认很强 |",
        "",
        "## 手续费门槛",
        "",
        "- 股票短线计划成交额低于 10,000 元：默认禁止开仓，太容易被最低 5 元佣金和卖出税费吃掉。",
        "- 股票短线计划成交额 10,000 到 20,000 元：默认不做，只允许 A 级强确认且次日流动性明确的单子。",
        f"- 股票短线常规试错门槛：单笔尽量不低于 {yuan(default_capital)} 元，这也是当前默认单票计划资金。",
        "- ETF 可保留更小试错仓，但也不鼓励把几百几千元碎单做成高频动作。",
        "",
        "## 涨停板目标的正确用法",
        "",
        "- 可以寻找接近涨停主线的早期共振票，但不能承诺每天买到涨停板。",
        "- 真正目标不是追涨停，而是找到：主线强、成交额足、回踩承接、T+1仍有退出空间的票。",
        "- 一字板、缩量秒板、尾盘情绪板默认不做，因为买不到或明天不好卖。",
        "- 如果没有 A/B 级动作卡，现金就是合格动作。",
        "",
        "## 今日动作卡",
        "",
    ]

    if watch_cards:
        lines.extend(
            [
                "| 标的 | 决策 | 等级 | 计划资金/股数 | 入场区 | 止损 | 风控 |",
                "| --- | --- | --- | ---: | --- | ---: | --- |",
                *[card_for_action(card) for card in watch_cards],
            ]
        )
    else:
        lines.append("当前没有最新动作卡；先运行 `python monitor.py` 或全系统 rerun。")

    if review["win_rate"] is not None:
        win_rate_line = f"- 复盘样本胜率：{review['win_rate']:.1f}%"
    else:
        win_rate_line = "- 复盘样本胜率：样本不足"

    lines.extend(
        [
            "",
            "## 今日是否允许进攻",
            "",
            f"- 可做动作卡数量：{len(do_cards)}",
            win_rate_line,
            f"- 已配对样本盈亏：{review['pnl_total']:.0f} 元",
            f"- 高频问题标签：{top_tags}",
            f"- 当前打开样本：{open_names}",
            "",
            "进攻条件：",
            "",
            "1. 今日没有触发软/硬熔断。",
            "2. 动作卡必须是 A/B 级，且不是单票孤立上涨。",
            "3. 股票短线单笔计划成交额低于 10,000 元的单子默认不做。",
            "4. 买入价在计划区内，不能因为月目标追高。",
            "5. 买入后立即写入真实交易日志和 T+1 处理线。",
            "",
            "## 当日记录要求",
            "",
            "- 每笔真实买入写入 `data/real_trade_journal.csv`。",
            "- 每个完成或打开的样本写入 `data/trade_review_samples.csv`。",
            "- 收盘后写 `reviews/daily/YYYY-MM-DD_trade_review.md`。",
            "- 如果 AI 建议触发交易，必须写清楚 `ai_responsibility`，用于改进流程。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local daily target card")
    parser.add_argument("--portfolio", default="", help="portfolio JSON path")
    parser.add_argument("--report", default="reports/latest.json", help="latest radar report")
    parser.add_argument("--review", default="data/trade_review_samples.csv", help="trade review sample CSV")
    parser.add_argument("--output", default="reports/daily_target_card.md", help="output markdown path")
    parser.add_argument("--monthly-target", type=float, default=float(os.getenv("MONTHLY_STOCK_PROFIT_TARGET", "60000")))
    parser.add_argument("--trading-days", type=int, default=int(os.getenv("MONTHLY_TRADING_DAYS", "20")))
    args = parser.parse_args()

    p_path = Path(args.portfolio) if args.portfolio else portfolio_path()
    if not p_path.is_absolute():
        p_path = ROOT / p_path
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    review_path = Path(args.review)
    if not review_path.is_absolute():
        review_path = ROOT / review_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    card = build_target_card(
        load_json(p_path),
        report_path,
        read_csv(review_path),
        monthly_target=args.monthly_target,
        trading_days=args.trading_days,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(card, encoding="utf-8")
    print(f"daily_target_card={output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
