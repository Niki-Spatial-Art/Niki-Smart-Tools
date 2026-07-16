#!/usr/bin/env python3
"""Small, auditable A-share quote and daily-bar router for local radar checks."""

from __future__ import annotations

import json
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any


TDX_SERVERS = [
    ("119.147.212.81", 7709),
    ("119.147.212.83", 7709),
    ("119.147.212.130", 7709),
    ("218.75.126.9", 7709),
]
USER_AGENT = "Mozilla/5.0 Niki-Smart-Tools A-share radar"


def normalize_code(value: str) -> str:
    code = "".join(char for char in str(value) if char.isdigit())
    if len(code) != 6:
        raise ValueError(f"Expected a six-digit A-share or ETF code, got {value!r}")
    return code


def market_prefix(code: str) -> str:
    return "sh" if code.startswith(("5", "6", "9")) else "sz"


def tencent_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [normalize_code(code) for code in codes]
    symbols = [market_prefix(code) + code for code in normalized]
    request = urllib.request.Request(
        "https://qt.gtimg.cn/q=" + ",".join(symbols), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        text = response.read().decode("gbk", "replace")

    rows: dict[str, dict[str, Any]] = {}
    for line in text.split(";"):
        if "~" not in line:
            continue
        symbol, _, quoted = line.partition('="')
        payload = quoted.rsplit('"', 1)[0]
        parts = payload.split("~")
        code = symbol.rsplit("_", 1)[-1][-6:]
        if len(code) != 6:
            continue

        def number(index: int) -> float | None:
            try:
                return float(parts[index])
            except (IndexError, TypeError, ValueError):
                return None

        price = number(3)
        previous_close = number(4)
        change_pct = number(32)
        if change_pct is None and price is not None and previous_close:
            change_pct = (price - previous_close) / previous_close * 100
        rows[code] = {
            "code": code,
            "name": parts[1] if len(parts) > 1 else code,
            "price": price,
            "previous_close": previous_close,
            "change_pct": change_pct,
            "amount": number(37),
            "quote_time": parts[30] if len(parts) > 30 else "",
            "source": "Tencent Finance quote",
        }
    return rows


def _tdx_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.2):
            return True
    except OSError:
        return False


def tdx_history(code: str, count: int) -> dict[str, Any]:
    try:
        from mootdx.quotes import Quotes
    except ImportError as exc:
        raise RuntimeError("mootdx is not installed") from exc

    client = None
    server = None
    for candidate in TDX_SERVERS:
        if _tdx_reachable(*candidate):
            client = Quotes.factory(market="std", server=candidate)
            server = candidate
            break
    if client is None:
        raise RuntimeError("No configured TongdaXin server is reachable")

    frame = client.bars(symbol=code, frequency=9, offset=count)
    if frame is None or frame.empty:
        raise RuntimeError("TongdaXin returned zero daily bars")
    columns = [column for column in ("datetime", "open", "high", "low", "close", "vol", "amount") if column in frame.columns]
    rows = json.loads(frame[columns].tail(count).to_json(orient="records", force_ascii=False))
    return {"source": "TongdaXin via mootdx", "server": f"{server[0]}:{server[1]}", "bars": rows}


def tencent_qfq_history(code: str, count: int) -> dict[str, Any]:
    symbol = market_prefix(code) + code
    query = urllib.parse.urlencode({"param": f"{symbol},day,,,{count},qfq"})
    request = urllib.request.Request(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + query,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = (payload.get("data") or {}).get(symbol) or {}
    raw_rows = data.get("qfqday") or data.get("day") or []
    if not raw_rows:
        raise RuntimeError("Tencent Finance returned no qfq daily bars")
    bars = []
    for row in raw_rows[-count:]:
        if len(row) < 6:
            continue
        bars.append({
            "date": row[0],
            "open": float(row[1]),
            "close": float(row[2]),
            "high": float(row[3]),
            "low": float(row[4]),
            "volume": float(row[5]),
        })
    if not bars:
        raise RuntimeError("Tencent Finance qfq bars were malformed")
    return {"source": "Tencent Finance qfq kline", "bars": bars}


def akshare_history(code: str, count: int) -> dict[str, Any]:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed") from exc

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=max(45, count * 3))).strftime("%Y%m%d")
    is_etf = code.startswith(("15", "16", "50", "51", "52", "56", "58"))
    if is_etf:
        frame = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
    else:
        frame = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
    if frame is None or frame.empty:
        raise RuntimeError("AKShare returned no daily bars")
    return {
        "source": f"AKShare {ak.__version__}",
        "bars": frame.tail(count).where(frame.notna(), None).to_dict(orient="records"),
    }


def history(code: str, count: int) -> dict[str, Any]:
    errors = []
    for label, fetcher in (
        ("TongdaXin via mootdx", tdx_history),
        ("Tencent Finance qfq kline", tencent_qfq_history),
        ("AKShare", akshare_history),
    ):
        try:
            payload = fetcher(code, count)
            payload["route"] = label
            payload["fallback_errors"] = errors
            return payload
        except Exception as exc:
            errors.append(f"{label}: {exc}")
    return {"error": "; ".join(errors), "route": "unavailable", "fallback_errors": errors}


def snapshot(codes: list[str], bars: int = 5) -> dict[str, Any]:
    normalized = list(dict.fromkeys(normalize_code(code) for code in codes))
    quotes = tencent_quotes(normalized)
    history_rows = {code: history(code, max(1, bars)) for code in normalized}
    for code, quote in quotes.items():
        bars_rows = (history_rows.get(code) or {}).get("bars") or []
        closes = []
        for row in bars_rows:
            value = row.get("close") if isinstance(row, dict) else None
            if value is None and isinstance(row, dict):
                value = row.get("收盘")
            try:
                closes.append(float(value))
            except (TypeError, ValueError):
                continue
        if len(closes) >= 20:
            quote["ma20"] = round(sum(closes[-20:]) / 20, 6)
        if len(closes) >= 60:
            quote["ma60"] = round(sum(closes[-60:]) / 60, 6)
    valid_quote_count = sum(1 for code in normalized if (quotes.get(code) or {}).get("price"))
    valid_history_count = sum(1 for payload in history_rows.values() if payload.get("bars"))
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "route": ["Tencent Finance quote", "TongdaXin via mootdx", "Tencent Finance qfq kline", "AKShare"],
        "requested_codes": normalized,
        "quotes": quotes,
        "history": history_rows,
        "status": {
            "valid_quote_count": valid_quote_count,
            "valid_history_count": valid_history_count,
            "quote_coverage_pct": round(valid_quote_count / len(normalized) * 100, 1) if normalized else 0,
            "history_coverage_pct": round(valid_history_count / len(normalized) * 100, 1) if normalized else 0,
        },
    }
