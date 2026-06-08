#!/usr/bin/env python3
"""Build an iFind-backed short-term review for holdings and strong-watch names."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.ifind_http import IFindHTTPClient
from tools.local_dashboard import BROKER as DEFAULT_BROKER_SNAPSHOT
from tools.local_dashboard import REPORT as DEFAULT_REPORT
from tools.local_dashboard import latest_snapshot, read_json
import monitor


SUFFIX_SH = {"5", "6", "9"}
IFIND_CLEAN_DIR = ROOT / "reports" / "ifind_clean"
PORTFOLIO_LOCAL = ROOT / "portfolio.local.json"


def load_local_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith(";"):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def latest_ifind_clean_radar_path() -> Path:
    rows = sorted(IFIND_CLEAN_DIR.glob("*_ifind_clean_radar.json"), key=lambda p: p.stat().st_mtime)
    return rows[-1] if rows else IFIND_CLEAN_DIR / "ifind_clean_radar_missing.json"


def ifind_code(code: str) -> str:
    code = str(code).strip()
    if "." in code:
        return code
    suffix = "SH" if code[:1] in SUFFIX_SH else "SZ"
    return f"{code}.{suffix}"


def plain_code(code: str) -> str:
    return str(code).split(".", 1)[0]


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def pct(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value * 100:.2f}%"


def price(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def money(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:,.0f} 元"


def mean(values: list[float]) -> float:
    valid = [v for v in values if not math.isnan(v)]
    return statistics.fmean(valid) if valid else math.nan


def median(values: list[float]) -> float:
    valid = [v for v in values if not math.isnan(v)]
    return statistics.median(valid) if valid else math.nan


def parse_history(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for table in payload.get("tables") or []:
        code = str(table.get("thscode") or "")
        times = table.get("time") or []
        data = table.get("table") or {}
        rows: list[dict[str, Any]] = []
        for i, dt in enumerate(times):
            row = {"date": dt, "code": code}
            for key, values in data.items():
                if isinstance(values, list) and i < len(values):
                    row[key] = as_float(values[i], math.nan)
            if not math.isnan(as_float(row.get("close"), math.nan)):
                rows.append(row)
        out[code] = rows
    return out


def parse_xingyao_history(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("rows") or []:
        code = plain_code(str(row.get("code") or ""))
        if code:
            grouped.setdefault(code, []).append(row)

    out: dict[str, list[dict[str, Any]]] = {}
    for code, rows in grouped.items():
        normalized: list[dict[str, Any]] = []
        prev_close = math.nan
        rows = sorted(rows, key=lambda r: str(r.get("kline_time") or r.get("date") or ""))
        for row in rows:
            close = as_float(row.get("close"), math.nan)
            change = (close / prev_close - 1) * 100 if prev_close and not math.isnan(close) else math.nan
            row_date = row.get("kline_time") or row.get("date")
            normalized.append(
                {
                    "date": str(row_date) if row_date is not None else "",
                    "code": code,
                    "open": as_float(row.get("open"), math.nan),
                    "high": as_float(row.get("high"), math.nan),
                    "low": as_float(row.get("low"), math.nan),
                    "close": close,
                    "volume": as_float(row.get("volume"), math.nan),
                    "amount": as_float(row.get("amount"), math.nan),
                    "changeRatio": change,
                }
            )
            if not math.isnan(close):
                prev_close = close
        out[code] = normalized
    return out


def ret(rows: list[dict[str, Any]], days: int) -> float:
    if len(rows) <= days:
        return math.nan
    now = as_float(rows[-1].get("close"), math.nan)
    prev = as_float(rows[-1 - days].get("close"), math.nan)
    return now / prev - 1 if prev and not math.isnan(prev) else math.nan


def rolling_state_backtest(rows: list[dict[str, Any]], lookback: int = 90) -> dict[str, Any]:
    if len(rows) < 25:
        return {"sample": 0, "next1_median": math.nan, "next1_win_rate": math.nan, "next2_median": math.nan, "next2_win_rate": math.nan}
    closes = [as_float(r.get("close"), math.nan) for r in rows]
    amounts = [as_float(r.get("amount"), math.nan) for r in rows]
    latest = rows[-1]
    latest_close = closes[-1]
    latest_ma20 = mean(closes[-20:])
    latest_above_ma20 = latest_close >= latest_ma20 if not math.isnan(latest_ma20) else False
    latest_day_ret = as_float(latest.get("changeRatio"), math.nan) / 100
    latest_amount_ratio = mean(amounts[-5:]) / mean(amounts[-20:]) if mean(amounts[-20:]) else math.nan
    cases_1d: list[float] = []
    cases_2d: list[float] = []
    start = max(20, len(rows) - lookback - 2)
    for i in range(start, len(rows) - 2):
        close_i = closes[i]
        ma20_i = mean(closes[i - 19 : i + 1])
        day_ret_i = as_float(rows[i].get("changeRatio"), math.nan) / 100
        amount_ratio_i = mean(amounts[i - 4 : i + 1]) / mean(amounts[i - 19 : i + 1]) if mean(amounts[i - 19 : i + 1]) else math.nan
        same_side = (close_i >= ma20_i) == latest_above_ma20 if not math.isnan(ma20_i) else False
        same_ret = (day_ret_i >= 0) == (latest_day_ret >= 0)
        similar_liquidity = math.isnan(latest_amount_ratio) or math.isnan(amount_ratio_i) or abs(amount_ratio_i - latest_amount_ratio) <= 0.7
        if same_side and same_ret and similar_liquidity:
            cases_1d.append(closes[i + 1] / close_i - 1)
            cases_2d.append(closes[i + 2] / close_i - 1)
    return {
        "sample": len(cases_1d),
        "next1_median": median(cases_1d),
        "next1_win_rate": sum(1 for x in cases_1d if x > 0) / len(cases_1d) if cases_1d else math.nan,
        "next2_median": median(cases_2d),
        "next2_win_rate": sum(1 for x in cases_2d if x > 0) / len(cases_2d) if cases_2d else math.nan,
    }


def strong_watch_codes(clean_radar: dict[str, Any]) -> set[str]:
    items = clean_radar.get("items") or []
    result = set()
    for item in items:
        if as_float(item.get("shares")) > 0:
            continue
        if as_float(item.get("trend_score")) >= 2 and as_float(item.get("dist_ma20"), -999) > 0:
            result.add(str(item.get("code") or ""))
    return result


def classify_tomorrow_action(summary: dict[str, Any], is_strong_watch: bool) -> tuple[str, str, str]:
    close = as_float(summary.get("close"), math.nan)
    protect = as_float(summary.get("protect_line"), math.nan)
    rebound = as_float(summary.get("rebound_line"), math.nan)
    distance_ma20 = as_float(summary.get("distance_ma20"), math.nan)
    day_ret = as_float(summary.get("change_ratio"), math.nan)
    ret20 = as_float(summary.get("ret_20d"), math.nan)
    regime = str(summary.get("regime") or "")
    bt = summary.get("similar_backtest") or {}
    win1 = as_float(bt.get("next1_win_rate"), math.nan)
    med2 = as_float(bt.get("next2_median"), math.nan)
    sample = int(as_float(bt.get("sample"), 0))
    shares = as_float(summary.get("position_shares"))

    if shares > 0:
        if not math.isnan(protect) and close <= protect:
            return "卖", f"跌破保护线 {price(protect)} 先减风险。", f"若次日仍弱，继续按保护线处理。"
        if regime in {"弱势下行", "震荡偏弱"} and med2 <= 0:
            return "等/减反弹", "仓位偏弱，优先等反弹减压，不补仓。", f"反弹观察 {price(rebound)} 一带。"
        if not math.isnan(win1) and win1 >= 0.55 and not math.isnan(distance_ma20) and distance_ma20 > 0:
            return "持有", "仍可先持有观察，但不是加仓指令。", f"只看承接，不追着加；反弹留意 {price(rebound)}。"
        return "等", "先处理已有仓位，不因为月目标硬开新动作。", f"守 {price(protect)}，反弹看 {price(rebound)}。"

    if not is_strong_watch:
        return "不做", "不是当前强势观察主池，明天默认不碰。", "保留观察即可。"
    if sample < 8:
        return "等", "回测样本太少，先不升级成买点。", "需要更多样本或更清楚的回踩结构。"
    if day_ret >= 0.05 or ret20 >= 0.20 or distance_ma20 >= 0.08:
        return "不买", "已经偏热，明天不追高。", f"只等回踩到 {price(rebound)} 附近再看。"
    if regime in {"强势延续", "震荡偏强"} and win1 >= 0.55 and med2 > 0:
        return "等回踩买", "强势但要等确认，不直接追。", f"明日观察回踩/承接区 {price(rebound)} 附近，守 {price(protect)}。"
    if win1 >= 0.5 and med2 >= 0:
        return "等", "结构还行，但胜率不够高，先看确认。", f"靠近 {price(rebound)} 再看承接。"
    return "不买", "回测不支持明天直接开仓。", "继续留在强势观察。"


def summarize_symbol(
    rows: list[dict[str, Any]],
    position: dict[str, Any] | None = None,
    is_strong_watch: bool = False,
) -> dict[str, Any]:
    closes = [as_float(r.get("close"), math.nan) for r in rows]
    highs = [as_float(r.get("high"), math.nan) for r in rows]
    lows = [as_float(r.get("low"), math.nan) for r in rows]
    amounts = [as_float(r.get("amount"), math.nan) for r in rows]
    latest = rows[-1] if rows else {}
    close = closes[-1] if closes else math.nan
    high20 = max([x for x in highs[-20:] if not math.isnan(x)], default=math.nan)
    low20 = min([x for x in lows[-20:] if not math.isnan(x)], default=math.nan)
    ma5 = mean(closes[-5:])
    ma10 = mean(closes[-10:])
    ma20 = mean(closes[-20:])
    avg_range10 = mean([(h - l) / c for h, l, c in zip(highs[-10:], lows[-10:], closes[-10:]) if c and not math.isnan(c)])
    amount_ratio = mean(amounts[-5:]) / mean(amounts[-20:]) if mean(amounts[-20:]) else math.nan
    drawdown20 = close / high20 - 1 if high20 and not math.isnan(high20) else math.nan
    distance_ma20 = close / ma20 - 1 if ma20 and not math.isnan(ma20) else math.nan
    trend_score = 0
    trend_score += 1 if close >= ma5 else -1
    trend_score += 1 if ma5 >= ma10 else -1
    trend_score += 1 if ma10 >= ma20 else -1
    trend_score += 1 if ret(rows, 5) > 0 else -1

    if trend_score >= 3:
        regime = "强势延续"
    elif trend_score >= 1:
        regime = "震荡偏强"
    elif trend_score <= -3:
        regime = "弱势下行"
    else:
        regime = "震荡偏弱"

    bt = rolling_state_backtest(rows)
    pos_cost = as_float((position or {}).get("cost"), math.nan)
    shares = as_float((position or {}).get("shares"), 0)
    unreal = (close - pos_cost) * shares if shares and not math.isnan(pos_cost) else math.nan
    stop_hint = close * (1 - max(avg_range10, 0.025)) if not math.isnan(avg_range10) else close * 0.975
    rebound_hint = close * (1 + max(avg_range10 * 0.6, 0.018)) if not math.isnan(avg_range10) else close * 1.018
    action, reason, plan = classify_tomorrow_action(
        {
            "close": close,
            "protect_line": stop_hint,
            "rebound_line": rebound_hint,
            "distance_ma20": distance_ma20,
            "change_ratio": as_float(latest.get("changeRatio"), math.nan) / 100,
            "ret_20d": ret(rows, 20),
            "regime": regime,
            "similar_backtest": bt,
            "position_shares": shares,
        },
        is_strong_watch=is_strong_watch,
    )
    return {
        "code": plain_code(str(latest.get("code") or "")),
        "ifind_code": latest.get("code"),
        "date": latest.get("date"),
        "close": close,
        "change_ratio": as_float(latest.get("changeRatio"), math.nan) / 100,
        "ret_3d": ret(rows, 3),
        "ret_5d": ret(rows, 5),
        "ret_10d": ret(rows, 10),
        "ret_20d": ret(rows, 20),
        "ret_60d": ret(rows, 60),
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "distance_ma20": distance_ma20,
        "drawdown20": drawdown20,
        "low20": low20,
        "high20": high20,
        "avg_range10": avg_range10,
        "amount_ratio_5_20": amount_ratio,
        "regime": regime,
        "trend_score": trend_score,
        "similar_backtest": bt,
        "position_shares": shares,
        "position_cost": pos_cost,
        "unrealized_estimate": unreal,
        "protect_line": stop_hint,
        "rebound_line": rebound_hint,
        "is_strong_watch": is_strong_watch,
        "tomorrow_action": action,
        "tomorrow_reason": reason,
        "tomorrow_plan": plan,
    }


def collect_codes(
    report: dict[str, Any],
    broker: dict[str, Any],
    portfolio_local: dict[str, Any],
    clean_radar: dict[str, Any],
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str], set[str]]:
    positions = broker.get("positions_visible") or []
    pos_by_plain = {str(p.get("code")): p for p in positions}
    names = {str(p.get("code")): str(p.get("name") or "") for p in positions}
    strong_watch = strong_watch_codes(clean_radar)
    codes: list[str] = []

    for p in positions:
        if as_float(p.get("shares")) > 0:
            codes.append(ifind_code(str(p.get("code"))))

    for item in portfolio_local.get("positions", []):
        code = str(item.get("code") or "")
        if code:
            pos_by_plain.setdefault(code, item)
            names.setdefault(code, str(item.get("name") or code))
            codes.append(ifind_code(code))

    for code in portfolio_local.get("watchlist", []):
        code = str(code or "")
        if code:
            codes.append(ifind_code(code))

    for card in ((report.get("action_stack") or {}).get("short_term_cards") or [])[:8]:
        code = str(card.get("code") or "")
        if code:
            codes.append(ifind_code(code))
            names.setdefault(code, str(card.get("name") or code))

    for item in clean_radar.get("items") or []:
        code = str(item.get("code") or "")
        if code:
            codes.append(ifind_code(code))
            names.setdefault(code, str(item.get("name") or code))

    deduped: list[str] = []
    for code in codes:
        if code and code not in deduped:
            deduped.append(code)
    return deduped, pos_by_plain, names, strong_watch


def build_markdown(payload: dict[str, Any]) -> str:
    rows = payload["summaries"]
    holdings = [r for r in rows if r["position_shares"] > 0]
    strong_watch = [r for r in rows if r["position_shares"] <= 0 and r.get("is_strong_watch")]
    buyable = [r for r in strong_watch if r.get("tomorrow_action") == "等回踩买"]
    buyable_summary = (
        " / ".join(f"{r['code']} {payload['names'].get(r['code'], r['code'])}" for r in buyable[:6])
        if buyable
        else "无可直接买入新票，默认等 / 不买。"
    )
    lines = [
        "# iFind 强势观察与持仓回测",
        "",
        f"生成时间：{payload['generated_at']}",
        f"数据区间：{payload['start_date']} 至 {payload['end_date']}；来源：iFind HTTP 历史行情。",
        "",
        "## 明日结论",
        "",
        f"- 持仓优先，先处理已有仓位 {len(holdings)} 只，不因为旧动作卡直接开新仓。",
        f"- 强势观察覆盖 {len(strong_watch)} 只；其中可进入“等回踩买”名单 {len(buyable)} 只。",
        f"- 明天默认结论：{buyable_summary}",
        "",
        "## 持仓处理",
        "",
        "| 代码 | 名称 | 收盘 | 状态 | 明日动作 | 原因 | 计划 |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for row in holdings:
        code = row["code"]
        lines.append(
            f"| {code} | {payload['names'].get(code, code)} | {price(row['close'])} | {row['regime']} | "
            f"{row['tomorrow_action']} | {row['tomorrow_reason']} | {row['tomorrow_plan']} |"
        )

    lines.extend(
        [
            "",
            "## 强势观察",
            "",
            "| 代码 | 名称 | 收盘 | 今日 | 20日 | MA20距离 | 回测样本 | 1日胜率 | 2日中位 | 明日动作 | 观察买点 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in strong_watch:
        code = row["code"]
        bt = row.get("similar_backtest") or {}
        lines.append(
            f"| {code} | {payload['names'].get(code, code)} | {price(row['close'])} | {pct(row['change_ratio'])} | "
            f"{pct(row['ret_20d'])} | {pct(row['distance_ma20'])} | {int(as_float(bt.get('sample'), 0))} | "
            f"{pct(as_float(bt.get('next1_win_rate'), math.nan))} | {pct(as_float(bt.get('next2_median'), math.nan))} | "
            f"{row['tomorrow_action']} | {row['tomorrow_plan']} |"
        )

    lines.extend(
        [
            "",
            "## 纪律",
            "",
            "- 强势观察不是追高名单。只有回踩确认、回测支持、量价不坏，才给到次日人工确认。",
            "- 如果次日高开急拉超过观察区，默认不追，继续等。",
            "- 本报告是本地纪律和回测辅助，不自动下单，不构成投资建议。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="iFind-backed holding and strong-watch backtest")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    load_local_env()
    report = read_json(DEFAULT_REPORT)
    broker = latest_snapshot(read_json(DEFAULT_BROKER_SNAPSHOT))
    portfolio_local = read_json(PORTFOLIO_LOCAL)
    clean_radar = read_json(latest_ifind_clean_radar_path())
    codes, positions, names, strong_watch = collect_codes(report, broker, portfolio_local, clean_radar)
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    source = "iFind HTTP history_quotes"
    raw_data: dict[str, Any] = {}
    try:
        xingyao_payload = monitor.fetch_xingyao_kline_rows(
            [plain_code(code) for code in codes],
            days=args.days,
            period="day",
        )
        if not xingyao_payload.get("row_count"):
            raise RuntimeError(xingyao_payload.get("error") or "empty Xingyao history")
        history = parse_xingyao_history(xingyao_payload)
        source = "Xingyao AmazingData daily kline"
        raw_data = {
            "xingyao_rows": xingyao_payload.get("row_count"),
            "xingyao_period": xingyao_payload.get("period"),
        }
    except (OSError, TimeoutError, RuntimeError) as xingyao_exc:
        client = IFindHTTPClient()
        payload = client.history_quotes(
            codes,
            indicators="open,high,low,close,volume,amount,changeRatio",
            start_date=start,
            end_date=end,
            functionpara={"Fill": "Blank"},
        )
        history = parse_history(payload)
        raw_data = {
            "raw_data_vol": payload.get("dataVol"),
            "xingyao_error": str(xingyao_exc),
        }
    summaries = []
    for code, rows in history.items():
        plain = plain_code(code)
        if not rows:
            continue
        summaries.append(summarize_symbol(rows, positions.get(plain), plain in strong_watch))

    summaries.sort(
        key=lambda r: (
            r["position_shares"] <= 0,
            not r.get("is_strong_watch"),
            0 if r.get("tomorrow_action") == "等回踩买" else 1,
            -as_float(r.get("trend_score")),
        )
    )

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": start,
        "end_date": end,
        "codes": codes,
        "names": names,
        "summaries": summaries,
        "source": source,
        **raw_data,
    }

    date_label = datetime.now().strftime("%Y-%m-%d")
    json_path = Path(args.output_json or ROOT / "reports" / f"ifind_position_backtest_{date_label}.json")
    md_path = Path(args.output_md or ROOT / "reports" / f"ifind_position_backtest_{date_label}.md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(out), encoding="utf-8-sig")
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")


if __name__ == "__main__":
    main()
