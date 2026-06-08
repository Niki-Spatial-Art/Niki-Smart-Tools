#!/usr/bin/env python3
"""Clean radar for holdings and focused watchlist.

This script intentionally avoids email and orders. It prefers free Xingyao
market data when available, falls back to iFind, then to latest local cache.
"""

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

from connectors.ifind_http import IFindHTTPClient, IFindHTTPError
import monitor

SUFFIX_SH = {"5", "6", "9"}

NAME_HINTS = {
    "002463": "沪电股份",
    "600110": "诺德股份",
    "513130": "恒生科技ETF",
    "159870": "化工ETF",
    "512100": "中证1000ETF",
    "588000": "科创50ETF",
    "600183": "生益科技",
    "518880": "黄金ETF华安",
    "512000": "券商ETF",
    "600066": "宇通客车",
    "002384": "东山精密",
    "002916": "深南电路",
    "603228": "景旺电子",
    "603083": "剑桥科技",
    "002747": "埃斯顿",
    "688676": "金盘科技",
    "002595": "豪迈科技",
    "603530": "神马电力",
}


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


def ifind_code(code: str) -> str:
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{'SH' if code[:1] in SUFFIX_SH else 'SZ'}"


def plain_code(code: str) -> str:
    return str(code).split(".", 1)[0]


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def mean(values: list[float]) -> float:
    values = [v for v in values if not math.isnan(v)]
    return statistics.fmean(values) if values else math.nan


def money(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:,.0f}"


def price(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    if abs(value) < 10:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def pct(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:.2f}%"


def parse_table_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for table in payload.get("tables") or []:
        code = plain_code(str(table.get("thscode") or ""))
        raw = table.get("table") or {}
        row: dict[str, Any] = {}
        for key, values in raw.items():
            row[key] = values[0] if isinstance(values, list) and values else values
        if code:
            out[code] = row
    return out


def parse_history(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for table in payload.get("tables") or []:
        code = plain_code(str(table.get("thscode") or ""))
        times = table.get("time") or []
        raw = table.get("table") or {}
        rows: list[dict[str, Any]] = []
        for i, dt in enumerate(times):
            row = {"date": dt, "code": code}
            for key, values in raw.items():
                if isinstance(values, list) and i < len(values):
                    row[key] = as_float(values[i])
            if not math.isnan(as_float(row.get("close"))):
                rows.append(row)
        if code:
            out[code] = rows
    return out


def xingyao_plain_code(code: str) -> str:
    return str(code).split(".", 1)[0]


def parse_xingyao_snapshot(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        code = xingyao_plain_code(str(row.get("code") or ""))
        latest = as_float(row.get("last"), math.nan)
        pre_close = as_float(row.get("pre_close"), math.nan)
        change = (latest / pre_close - 1) * 100 if pre_close and not math.isnan(latest) else math.nan
        if code:
            out[code] = {
                "latest": latest,
                "changeRatio": change,
                "amount": as_float(row.get("amount"), math.nan),
            }
    return out


def parse_xingyao_history(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in payload.get("rows") or []:
        code = xingyao_plain_code(str(row.get("code") or ""))
        if not code:
            continue
        grouped.setdefault(code, []).append(row)
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


def build_items(
    codes: list[str],
    positions: dict[str, Any],
    portfolio: dict[str, Any],
    realtime: dict[str, Any],
    history: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    total_capital = as_float(portfolio.get("total_capital"), 0)
    items = []
    for code in codes:
        pos = positions.get(code)
        name = str((pos or {}).get("name") or NAME_HINTS.get(code) or code)
        items.append(
            summarize_code(
                code=code,
                name=name,
                realtime=realtime.get(code, {}),
                history=history.get(code, []),
                position=pos,
                total_capital=total_capital,
            )
        )
    return items


def build_xingyao_payload(portfolio: dict[str, Any], codes: list[str], days: int) -> dict[str, Any]:
    snapshot_payload = monitor.fetch_xingyao_snapshot_rows(codes)
    if not snapshot_payload.get("row_count"):
        raise RuntimeError(f"Xingyao snapshot unavailable: {snapshot_payload.get('error') or 'empty'}")
    history_payload = monitor.fetch_xingyao_kline_rows(codes, days=days, period="day")
    if not history_payload.get("row_count"):
        raise RuntimeError(f"Xingyao daily kline unavailable: {history_payload.get('error') or 'empty'}")

    realtime = parse_xingyao_snapshot(snapshot_payload)
    history = parse_xingyao_history(history_payload)
    positions = {str(x.get("code")): x for x in portfolio.get("positions", [])}
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Xingyao AmazingData snapshot + daily kline",
        "warning": "-",
        "portfolio": portfolio,
        "items": build_items(codes, positions, portfolio, realtime, history),
        "raw": {
            "snapshot_rows": snapshot_payload.get("row_count"),
            "history_rows": history_payload.get("row_count"),
            "history_period": history_payload.get("period"),
            "data_router": "xingyao -> ifind -> cache",
        },
    }


def build_ifind_payload(
    portfolio: dict[str, Any],
    codes: list[str],
    ifind_codes: list[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    client = IFindHTTPClient()
    realtime_payload = client.realtime_quotes(ifind_codes)
    history_payload = client.history_quotes(
        ifind_codes,
        indicators="open,high,low,close,volume,amount,changeRatio",
        start_date=start,
        end_date=end,
        functionpara={"Fill": "Blank"},
    )
    realtime = parse_table_payload(realtime_payload)
    history = parse_history(history_payload)
    positions = {str(x.get("code")): x for x in portfolio.get("positions", [])}
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "iFind HTTP realtime_quotes + history_quotes",
        "warning": "-",
        "portfolio": portfolio,
        "items": build_items(codes, positions, portfolio, realtime, history),
        "raw": {
            "realtime_dataVol": realtime_payload.get("dataVol"),
            "history_dataVol": history_payload.get("dataVol"),
            "data_router": "xingyao -> ifind -> cache",
        },
    }


def ret(rows: list[dict[str, Any]], days: int) -> float:
    if len(rows) <= days:
        return math.nan
    now = as_float(rows[-1].get("close"))
    prev = as_float(rows[-1 - days].get("close"))
    return (now / prev - 1) * 100 if prev and not math.isnan(prev) else math.nan


def summarize_code(
    code: str,
    name: str,
    realtime: dict[str, Any],
    history: list[dict[str, Any]],
    position: dict[str, Any] | None,
    total_capital: float,
) -> dict[str, Any]:
    close = as_float(realtime.get("latest"), math.nan)
    if math.isnan(close) and history:
        close = as_float(history[-1].get("close"))
    closes = [as_float(r.get("close")) for r in history]
    highs = [as_float(r.get("high")) for r in history]
    amounts = [as_float(r.get("amount")) for r in history]

    ma5 = mean(closes[-5:])
    ma10 = mean(closes[-10:])
    ma20 = mean(closes[-20:])
    ma60 = mean(closes[-60:])
    high20 = max([v for v in highs[-20:] if not math.isnan(v)], default=math.nan)
    amount_ratio = mean(amounts[-5:]) / mean(amounts[-20:]) if mean(amounts[-20:]) else math.nan
    trend_score = 0
    if not math.isnan(close) and not math.isnan(ma5):
        trend_score += 1 if close >= ma5 else -1
    if not math.isnan(ma5) and not math.isnan(ma10):
        trend_score += 1 if ma5 >= ma10 else -1
    if not math.isnan(ma10) and not math.isnan(ma20):
        trend_score += 1 if ma10 >= ma20 else -1
    if not math.isnan(ma20) and not math.isnan(ma60):
        trend_score += 1 if ma20 >= ma60 else -1

    shares = as_float((position or {}).get("shares"), 0)
    cost = as_float((position or {}).get("cost"))
    value = close * shares if shares and not math.isnan(close) else 0.0
    pnl = (close - cost) * shares if shares and not math.isnan(cost) and not math.isnan(close) else math.nan
    weight = value / total_capital * 100 if total_capital else math.nan
    buy_below = as_float((position or {}).get("buy_below"))
    if not math.isnan(buy_below) and buy_below <= 0:
        buy_below = math.nan
    sell_above = as_float((position or {}).get("sell_above"))
    stop_loss = as_float((position or {}).get("stop_loss"))

    decision = "观察"
    reason = "非持仓或未触发动作"
    if shares > 0:
        if not math.isnan(stop_loss) and close <= stop_loss:
            decision = "检查止损"
            reason = f"价格 {price(close)} <= 止损线 {price(stop_loss)}"
        elif not math.isnan(sell_above) and close >= sell_above:
            decision = "分批止盈/减压"
            reason = f"价格 {price(close)} >= 处理线 {price(sell_above)}"
        elif math.isnan(buy_below):
            decision = "持仓管理"
            reason = "当前设为不加仓，只管理修复/减压/止损"
        elif close <= buy_below:
            decision = "到买入线，仍需人工确认"
            reason = f"价格 {price(close)} <= 买入线 {price(buy_below)}"
        else:
            decision = "持有观察"
            reason = "未到买入/卖出/止损触发线"
    elif not math.isnan(close) and not math.isnan(ma20) and close > ma20 and trend_score >= 2:
        decision = "强势观察"
        reason = "趋势偏强，但不是持仓，不追高"

    return {
        "code": code,
        "name": name,
        "close": close,
        "change": as_float(realtime.get("changeRatio")),
        "turnover": as_float(realtime.get("turnoverRatio")),
        "amount": as_float(realtime.get("amount")),
        "ret5": ret(history, 5),
        "ret20": ret(history, 20),
        "dist_ma20": (close / ma20 - 1) * 100 if ma20 and not math.isnan(close) else math.nan,
        "drawdown20": (close / high20 - 1) * 100 if high20 and not math.isnan(close) else math.nan,
        "amount_ratio": amount_ratio,
        "trend_score": trend_score,
        "shares": shares,
        "cost": cost,
        "value": value,
        "weight": weight,
        "pnl": pnl,
        "buy_below": buy_below,
        "sell_above": sell_above,
        "stop_loss": stop_loss,
        "decision": decision,
        "reason": reason,
        "note": str((position or {}).get("note") or ""),
    }


def build_markdown(payload: dict[str, Any]) -> str:
    portfolio = payload["portfolio"]
    holdings = [x for x in payload["items"] if x["shares"] > 0]
    watch = [x for x in payload["items"] if x["shares"] <= 0]
    lines = [
        "# Clean Radar",
        "",
        f"生成时间：{payload['generated_at']}",
        f"数据源：{payload.get('source') or '-'}。未发送邮件，未自动下单。",
        "",
        "## 资金口径",
        "",
        "| 项目 | 数值 |",
        "| --- | ---: |",
        f"| 券商账户资产 | {money(as_float(portfolio.get('broker_total_capital')))} |",
        f"| 场外待转入 | {money(as_float(portfolio.get('external_cash_pending'), 0))} |",
        f"| 规划总资金 | {money(as_float(portfolio.get('total_capital')))} |",
        f"| 账户现金 | {money(as_float(portfolio.get('cash')))} |",
        f"| 持仓市值 | {money(as_float(portfolio.get('securities_market_value')))} |",
        "",
        "## 持仓动作卡",
        "",
        "| 代码 | 名称 | 收盘/最新 | 涨跌 | 仓位 | 浮盈亏估算 | 5日 | 20日 | MA20距离 | 决策 | 原因 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for x in holdings:
        lines.append(
            f"| {x['code']} | {x['name']} | {price(x['close'])} | {pct(x['change'])} | "
            f"{pct(x['weight'])} | {money(x['pnl'])} | {pct(x['ret5'])} | {pct(x['ret20'])} | "
            f"{pct(x['dist_ma20'])} | {x['decision']} | {x['reason']} |"
        )
    lines.extend(
        [
            "",
            "## 观察池",
            "",
            "| 代码 | 名称 | 收盘/最新 | 涨跌 | 5日 | 20日 | MA20距离 | 量能5/20 | 决策 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for x in watch:
        lines.append(
            f"| {x['code']} | {x['name']} | {price(x['close'])} | {pct(x['change'])} | "
            f"{pct(x['ret5'])} | {pct(x['ret20'])} | {pct(x['dist_ma20'])} | "
            f"{x['amount_ratio']:.2f} | {x['decision']} |"
        )
    lines.extend(
        [
            "",
            "## 明日优先级",
            "",
            "1. 先处理已有持仓，不因为旧报告乱码或现金焦虑新增战线。",
            "2. 沪电股份仍按失败试仓纪律管理：不加仓，先看 132.8 修复，134 附近弱反弹减压，127 失败线。",
            "3. 恒生科技 ETF 是账户拖累源之一，未修复 0.64/0.65 前不加。",
            "4. PCB/覆铜板/AI硬件主线继续观察，但只等回踩确认，不追 5% 以上急拉。",
            "",
            "## 使用提醒",
            "",
            "旧的 etf_radar 报告包含东方财富代理噪音和修复前的除零错误，不再作为当前判断依据。以后优先看本报告。",
        ]
    )
    return "\n".join(lines) + "\n"


def latest_cached_payload(out_dir: Path) -> dict[str, Any] | None:
    paths = sorted(out_dir.glob("*_ifind_clean_radar.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(paths):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def build_degraded_payload(
    portfolio: dict[str, Any],
    codes: list[str],
    out_dir: Path,
    error: Exception,
) -> dict[str, Any]:
    cached = latest_cached_payload(out_dir) or {}
    cached_items = {
        str(item.get("code") or ""): dict(item)
        for item in cached.get("items", [])
        if item.get("code")
    }
    positions = {str(x.get("code")): x for x in portfolio.get("positions", [])}
    total_capital = as_float(portfolio.get("total_capital"), 0)
    items: list[dict[str, Any]] = []
    for code in codes:
        pos = positions.get(code)
        base = cached_items.get(code, {})
        name = str((pos or {}).get("name") or base.get("name") or NAME_HINTS.get(code) or code)
        close = as_float(base.get("close"), math.nan)
        shares = as_float((pos or {}).get("shares"), 0)
        cost = as_float((pos or {}).get("cost"))
        value = close * shares if shares and not math.isnan(close) else 0.0
        pnl = (close - cost) * shares if shares and not math.isnan(cost) and not math.isnan(close) else math.nan
        weight = value / total_capital * 100 if total_capital else math.nan
        stop_loss = as_float((pos or {}).get("stop_loss"))
        sell_above = as_float((pos or {}).get("sell_above"))
        buy_below = as_float((pos or {}).get("buy_below"), math.nan)

        item = dict(base)
        item.update(
            {
                "code": code,
                "name": name,
                "shares": shares,
                "cost": cost,
                "value": value,
                "weight": weight,
                "pnl": pnl,
                "buy_below": buy_below,
                "sell_above": sell_above,
                "stop_loss": stop_loss,
                "note": str((pos or {}).get("note") or base.get("note") or ""),
            }
        )
        if shares > 0:
            if not math.isnan(close) and not math.isnan(stop_loss) and close <= stop_loss:
                item["decision"] = "STALE-CACHE: check stop / reduce risk"
                item["reason"] = f"cached price {price(close)} <= stop {price(stop_loss)}; verify live quote before action"
            else:
                item["decision"] = "STALE-CACHE: hold / verify"
                item["reason"] = "iFind unavailable; manage existing position only, no add"
        else:
            item["decision"] = "STALE-CACHE: watch only"
            item["reason"] = "iFind unavailable; buy candidates are disabled"
        items.append(item)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": f"DEGRADED: latest cached clean radar + current portfolio.local.json ({error})",
        "warning": "Fresh iFind data unavailable. All buy candidates are disabled until live data is restored.",
        "portfolio": portfolio,
        "items": items,
        "raw": {
            "fallback": True,
            "fallback_error": str(error),
            "cached_generated_at": cached.get("generated_at", ""),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an iFind-only clean radar report")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "ifind_clean"))
    args = parser.parse_args()

    load_local_env()
    portfolio = read_json(ROOT / "portfolio.local.json")
    positions = {str(x.get("code")): x for x in portfolio.get("positions", [])}
    codes: list[str] = []
    for item in portfolio.get("positions", []):
        code = str(item.get("code") or "").strip()
        if code and code not in codes:
            codes.append(code)
    for code in portfolio.get("watchlist", []):
        code = str(code).strip()
        if code and code not in codes:
            codes.append(code)

    ifind_codes = [ifind_code(code) for code in codes]
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        payload = build_xingyao_payload(portfolio, codes, args.days)
    except (OSError, TimeoutError, RuntimeError) as xingyao_exc:
        try:
            payload = build_ifind_payload(portfolio, codes, ifind_codes, start, end)
            payload["warning"] = f"Xingyao unavailable; used iFind fallback. Xingyao error: {xingyao_exc}"
            payload.setdefault("raw", {})["xingyao_error"] = str(xingyao_exc)
        except (IFindHTTPError, OSError, TimeoutError, RuntimeError) as exc:
            payload = build_degraded_payload(portfolio, codes, out_dir, exc)
            payload.setdefault("raw", {})["xingyao_error"] = str(xingyao_exc)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = out_dir / f"{stamp}_ifind_clean_radar.json"
    md_path = out_dir / f"{stamp}_ifind_clean_radar.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(payload), encoding="utf-8-sig")

    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    print("Open with: notepad " + str(md_path))


if __name__ == "__main__":
    main()
