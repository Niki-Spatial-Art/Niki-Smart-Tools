#!/usr/bin/env python3
"""ETF Strategy Monitor.

This script checks a focused ETF watchlist, labels each ETF as green/yellow/red,
adds an optional AI summary, and sends a short email report.
"""

import html
import contextlib
import csv
import io
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from math import log10
from statistics import mean
from typing import Dict, List, Optional

import pytz
import requests

from ai_client import generate_ai_summary
from emailer import EmailNotifier


def load_local_env(path: str = ".env") -> None:
    """Load local KEY=VALUE settings for Windows Task Scheduler runs."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BEIJING_TZ = pytz.timezone("Asia/Shanghai")


DEFAULT_WATCHLIST = [
    "513310",  # China-Korea Semiconductor ETF, red-light risk sample
    "159696",  # Nasdaq 100 ETF QDII
    "513500",  # S&P 500 ETF QDII
    "510300",  # CSI 300 ETF
    "510500",  # CSI 500 ETF
    "512100",  # CSI 1000 ETF
    "512880",  # Securities ETF
    "588000",  # STAR 50 ETF
    "512760",  # Semiconductor ETF
    "513180",  # Hang Seng Tech ETF
    "518880",  # Gold ETF
]

DEFAULT_OPTION_ETF_WATCHLIST = ["510300", "588000", "512100", "510050"]
DEFAULT_HIGH_RISK_CODES = {"513310"}
DEFAULT_QDII_CODES = {"513310", "159696", "513180", "513500"}
DEFAULT_PORTFOLIO_FILE = "portfolio.local.json" if Path("portfolio.local.json").exists() else "portfolio.example.json"
PORTFOLIO_FILE = os.getenv("PORTFOLIO_FILE", DEFAULT_PORTFOLIO_FILE)
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")
XINGYAO_CACHE_PATH = os.getenv("XINGYAO_CACHE_PATH", "data/xingyao_option_basic_cache.json")
DIGITAL_INFRA_FILE = os.getenv("DIGITAL_INFRA_FILE", "digital_infra_watchlist.json")
IFIND_HTTP_PROBE_PATH = os.getenv("IFIND_HTTP_PROBE_PATH", "data/latest_ifind_http_probe.json")
PAPER_TRADE_JOURNAL_PATH = os.getenv("PAPER_TRADE_JOURNAL_PATH", "data/paper_trade_journal.csv")
EXECUTION_EVENTS_PATH = os.getenv("EXECUTION_EVENTS_PATH", "data/execution_events.json")


def env_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


WINDPY_CLIENT = None
WINDPY_CONNECT_ATTEMPTED = False


def wind_enabled() -> bool:
    return env_enabled("WIND_ENABLED", "false")


def windpy_client():
    global WINDPY_CLIENT, WINDPY_CONNECT_ATTEMPTED
    if not wind_enabled():
        raise RuntimeError("WIND_ENABLED is false")
    if WINDPY_CLIENT is not None:
        return WINDPY_CLIENT
    if WINDPY_CONNECT_ATTEMPTED:
        raise RuntimeError("WindPy unavailable")

    WINDPY_CONNECT_ATTEMPTED = True
    try:
        from WindPy import w  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"WindPy import failed: {exc}") from exc

    wait_time = int(os.getenv("WIND_WAIT_TIME", "30"))
    result = w.start(waitTime=wait_time)
    error_code = getattr(result, "ErrorCode", -1)
    if error_code != 0 or not w.isconnected():
        raise RuntimeError(f"WindPy start failed: error={error_code}")
    WINDPY_CLIENT = w
    return WINDPY_CLIENT


def load_json_file(path: str | Path) -> Dict:
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def load_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


@dataclass
class Quote:
    code: str
    name: str
    price: Optional[float]
    pct_change: Optional[float]
    amount: Optional[float]
    ma20: Optional[float]
    ma60: Optional[float]
    premium: Optional[float] = None


def split_env_set(name: str, default_values: set) -> set:
    raw = os.getenv(name)
    if not raw:
        return set(default_values)
    return {item.strip() for item in raw.split(",") if item.strip()}


def market_prefix(code: str) -> str:
    return "1" if code.startswith(("5", "6", "9")) else "0"


def secid(code: str) -> str:
    return f"{market_prefix(code)}.{code}"


def market_code(code: str) -> str:
    return f"sh{code}" if market_prefix(code) == "1" else f"sz{code}"


def safe_float(value, scale: float = 1.0) -> Optional[float]:
    try:
        if value in (None, "-", ""):
            return None
        return float(value) / scale
    except (TypeError, ValueError):
        return None


def first_float(row: Dict, *keys: str, scale: float = 1.0) -> Optional[float]:
    for key in keys:
        if key in row:
            value = safe_float(row.get(key), scale)
            if value is not None:
                return value
    return None


def eastmoney_price_float(code: str, value) -> Optional[float]:
    if code.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "588", "159")):
        return safe_float(value, 1000)
    return safe_float(value, 100)


def eastmoney_get(
    url: str,
    params: Dict,
    timeout: int = 18,
    retries: int = 3,
    warn: bool = True,
) -> Dict:
    headers = {
        "User-Agent": "Mozilla/5.0 ETF Strategy Monitor",
        "Referer": "https://quote.eastmoney.com/",
    }
    last_exc = None
    urls = [url]
    if "push2.eastmoney.com" in url:
        urls.append(url.replace("push2.eastmoney.com", "push2delay.eastmoney.com"))
    elif "push2delay.eastmoney.com" in url:
        urls.append(url.replace("push2delay.eastmoney.com", "push2.eastmoney.com"))

    for attempt in range(retries):
        for candidate in urls:
            try:
                response = requests.get(candidate, params=params, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_exc = exc
                if warn:
                    logger.warning("Eastmoney request failed (%s/%s): %s", attempt + 1, candidate, exc)
        time.sleep(1 + attempt)
    raise last_exc


def fetch_quote_eastmoney(code: str) -> Quote:
    data = eastmoney_get(
        "https://push2.eastmoney.com/api/qt/stock/get",
        {
            "secid": secid(code),
            "fields": "f57,f58,f43,f170,f48",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        },
    ).get("data") or {}

    name = data.get("f58") or code
    price = eastmoney_price_float(code, data.get("f43"))
    pct_change = safe_float(data.get("f170"), 100)
    amount = safe_float(data.get("f48"), 1)

    ma20, ma60 = fetch_moving_averages(code)

    return Quote(
        code=code,
        name=name,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def fetch_quote_tencent(code: str) -> Quote:
    url = "https://qt.gtimg.cn/q=" + market_code(code)
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 ETF Strategy Monitor"},
        timeout=12,
    )
    response.raise_for_status()
    response.encoding = "gbk"
    text = response.text.strip()
    if "~" not in text:
        raise ValueError(f"Unexpected Tencent quote format for {code}")

    payload = text.split('"', 1)[1].rsplit('"', 1)[0]
    parts = payload.split("~")
    name = parts[1] if len(parts) > 1 and parts[1] else code
    price = safe_float(parts[3] if len(parts) > 3 else None)
    pct_change = safe_float(parts[32] if len(parts) > 32 else None)
    amount = safe_float(parts[37] if len(parts) > 37 else None, 0.0001)
    ma20, ma60 = fetch_moving_averages(code)

    return Quote(
        code=code,
        name=name,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def fetch_quote_sina(code: str) -> Quote:
    url = "https://hq.sinajs.cn/list=" + market_code(code)
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ETF Strategy Monitor",
            "Referer": "https://finance.sina.com.cn/",
        },
        timeout=12,
    )
    response.raise_for_status()
    response.encoding = "gbk"
    text = response.text.strip()
    if "," not in text:
        raise ValueError(f"Unexpected Sina quote format for {code}")

    payload = text.split('"', 1)[1].rsplit('"', 1)[0]
    parts = payload.split(",")
    name = parts[0] if parts and parts[0] else code
    open_price = safe_float(parts[1] if len(parts) > 1 else None)
    prev_close = safe_float(parts[2] if len(parts) > 2 else None)
    price = safe_float(parts[3] if len(parts) > 3 else None)
    amount = safe_float(parts[9] if len(parts) > 9 else None)
    pct_change = ((price - prev_close) / prev_close * 100) if price and prev_close else None
    if price is None and open_price is not None:
        price = open_price
    ma20, ma60 = fetch_moving_averages(code)

    return Quote(
        code=code,
        name=name,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def fetch_quote_yahoo(code: str) -> Quote:
    suffix = ".SS" if market_prefix(code) == "1" else ".SZ"
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{code}{suffix}",
        params={"range": "5d", "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0 ETF Strategy Monitor"},
        timeout=12,
    )
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0] or {}
    meta = result.get("meta") or {}
    price = safe_float(meta.get("regularMarketPrice"))
    prev_close = safe_float(meta.get("previousClose"))
    pct_change = ((price - prev_close) / prev_close * 100) if price and prev_close else None
    volume = safe_float(meta.get("regularMarketVolume"))
    amount = price * volume if price is not None and volume is not None else None
    ma20, ma60 = fetch_moving_averages(code)

    return Quote(
        code=code,
        name=meta.get("symbol") or code,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def quote_from_xingyao_row(code: str, row: Dict) -> Quote:
    name = (
        row.get("security_name")
        or row.get("SECURITY_NAME")
        or row.get("name")
        or row.get("Name")
        or code
    )
    price = first_float(
        row,
        "last_price",
        "LAST_PRICE",
        "close_price",
        "CLOSE_PRICE",
        "last",
        "price",
    )
    pre_close = first_float(row, "pre_close_price", "PRE_CLOSE_PRICE", "pre_close", "prev_close", "preclose")
    pct_change = first_float(row, "pct_change", "PCT_CHANGE", "change_rate")
    if pct_change is None and price is not None and pre_close:
        pct_change = (price - pre_close) / pre_close * 100
    amount = first_float(row, "total_value_trade", "TOTAL_VALUE_TRADE", "amount", "AMOUNT")
    return Quote(
        code=code,
        name=str(name),
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=None,
        ma60=None,
    )


def fetch_quote_xingyao(code: str) -> Quote:
    snapshot = fetch_xingyao_snapshot_rows([code])
    rows = snapshot.get("rows") or []
    if not rows:
        error = snapshot.get("error") or "empty snapshot"
        raise RuntimeError(error)
    quote = quote_from_xingyao_row(code, rows[0])
    if quote.price is None:
        raise RuntimeError("Xingyao snapshot missing price")
    quote.ma20, quote.ma60 = fetch_moving_averages(code)
    return quote


def fetch_quote_wind(code: str) -> Quote:
    client = windpy_client()
    result = client.wsq(code, "rt_last,rt_pct_chg,rt_amt,sec_name")
    error_code = getattr(result, "ErrorCode", -1)
    if error_code != 0:
        raise RuntimeError(f"Wind wsq failed: error={error_code}")

    fields = [str(field).upper() for field in (getattr(result, "Fields", None) or [])]
    data = getattr(result, "Data", None) or []
    if not fields or not data:
        raise RuntimeError("Wind wsq returned empty payload")

    payload = {}
    for idx, field in enumerate(fields):
        values = data[idx] if idx < len(data) else []
        payload[field] = values[0] if values else None

    price = safe_float(payload.get("RT_LAST"))
    pct_change = safe_float(payload.get("RT_PCT_CHG"))
    amount = safe_float(payload.get("RT_AMT"))
    name = str(payload.get("SEC_NAME") or code)
    if price is None:
        raise RuntimeError("Wind wsq missing RT_LAST")

    ma20, ma60 = fetch_moving_averages(code)
    return Quote(
        code=code,
        name=name,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def fetch_quote(code: str) -> Quote:
    sources = [
        ("xingyao", fetch_quote_xingyao),
        ("wind", fetch_quote_wind),
        ("eastmoney", fetch_quote_eastmoney),
        ("tencent", fetch_quote_tencent),
        ("sina", fetch_quote_sina),
        ("yahoo", fetch_quote_yahoo),
    ]
    errors = []
    for source_name, fetcher in sources:
        if source_name == "xingyao" and not env_enabled("XINGYAO_QUOTE_PRIORITY", "false"):
            continue
        if source_name == "wind" and not wind_enabled():
            continue
        try:
            quote = fetcher(code)
            if quote.price is None:
                raise ValueError("missing price")
            logger.info("%s quote source: %s", code, source_name)
            return quote
        except Exception as exc:
            logger.warning("%s quote source %s failed: %s", code, source_name, exc)
            errors.append(f"{source_name}: {exc}")
    raise RuntimeError("; ".join(errors))


def load_option_etf_watchlist() -> List[str]:
    raw = os.getenv("OPTION_ETF_WATCHLIST", "")
    if not raw:
        return DEFAULT_OPTION_ETF_WATCHLIST
    return [item.strip() for item in raw.split(",") if item.strip()]


def fourth_wednesday(year: int, month: int) -> datetime:
    day = datetime(year, month, 1)
    wednesdays = []
    while day.month == month:
        if day.weekday() == 2:
            wednesdays.append(day)
        day += timedelta(days=1)
    return BEIJING_TZ.localize(wednesdays[3])


def next_option_expiry(now: datetime) -> datetime:
    expiry = fourth_wednesday(now.year, now.month).replace(hour=15, minute=0, second=0, microsecond=0)
    if now >= expiry:
        next_month = 1 if now.month == 12 else now.month + 1
        next_year = now.year + 1 if now.month == 12 else now.year
        expiry = fourth_wednesday(next_year, next_month).replace(hour=15, minute=0, second=0, microsecond=0)
    return expiry


def option_strike_step(price: float) -> float:
    if price < 3:
        return 0.05
    if price < 5:
        return 0.1
    return 0.25


def nearest_option_strike(price: float) -> float:
    step = option_strike_step(price)
    return round(round(price / step) * step, 3)


def estimate_option_premium(price: float, days_to_expiry: int, direction: str) -> float:
    base_vol = float(os.getenv("OPTION_SIM_BASE_VOL", "0.24"))
    time_value = price * base_vol * max((days_to_expiry / 365) ** 0.5, 0.04) * 0.35
    floor = float(os.getenv("OPTION_SIM_MIN_PREMIUM", "0.015"))
    direction_buffer = 1.05 if direction == "认沽" else 1.0
    return round(max(time_value * direction_buffer, floor), 4)


def option_payoff(price: float, strike: float, premium: float, direction: str, move_pct: float) -> Dict:
    future_price = price * (1 + move_pct / 100)
    intrinsic = max(future_price - strike, 0) if direction == "认购" else max(strike - future_price, 0)
    return {
        "move_pct": move_pct,
        "future_price": future_price,
        "profit": (intrinsic - premium) * 10000,
    }


def option_time_risk(days_to_expiry: int, premium: float) -> str:
    daily_decay = premium * 10000 / max(days_to_expiry, 1)
    if days_to_expiry <= 7:
        level = "高"
    elif days_to_expiry <= 21:
        level = "中"
    else:
        level = "低"
    return f"{level}：估算每天时间损耗约{yuan(daily_decay)}，越临近到期越快"


def xingyao_sdk_paths() -> List[str]:
    raw = os.getenv("XINGYAO_SDK_PATHS", "")
    paths = [item.strip() for item in raw.split(os.pathsep) if item.strip()]
    sdk_root = os.getenv("XINGYAO_SDK_ROOT", "").strip()
    if sdk_root:
        root = Path(sdk_root).expanduser()
        paths.extend([str(root / "amazingdata_sdk"), str(root / "xingyao_sdk")])
    return paths


def add_xingyao_sdk_paths() -> None:
    for sdk_path in xingyao_sdk_paths():
        if sdk_path and os.path.exists(sdk_path) and sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)


def xingyao_cache_path() -> Path:
    return Path(XINGYAO_CACHE_PATH).expanduser()


def xingyao_cache_payload(payload: Dict) -> Dict:
    clean_payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    clean_payload["cache_updated_at"] = datetime.now(BEIJING_TZ).isoformat()
    clean_payload["cache_schema"] = 1
    return clean_payload


def save_xingyao_option_cache(payload: Dict) -> None:
    path = xingyao_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming_contracts = payload.get("contracts") or []
    incoming_count = len(incoming_contracts) if isinstance(incoming_contracts, list) else 0
    existing_count = 0
    if path.exists():
        try:
            existing_payload = json.loads(path.read_text(encoding="utf-8"))
            existing_contracts = existing_payload.get("contracts") or []
            existing_count = len(existing_contracts) if isinstance(existing_contracts, list) else 0
        except Exception:
            existing_count = 0
    if existing_count >= 1000 and incoming_count < existing_count * 0.8:
        logger.warning(
            "Skip narrowing Xingyao option cache: incoming=%s existing=%s",
            incoming_count,
            existing_count,
        )
        return
    path.write_text(
        json.dumps(xingyao_cache_payload(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Xingyao option cache saved: %s", path)


def load_xingyao_option_cache() -> Optional[Dict]:
    path = xingyao_cache_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Xingyao option cache read failed: %s", exc)
        return {
            "enabled": False,
            "source": "simulation",
            "contracts": [],
            "error": f"cache read failed: {exc}",
        }

    contracts = payload.get("contracts") or []
    if not isinstance(contracts, list):
        contracts = []

    payload["enabled"] = bool(contracts)
    payload["source"] = "xingyao_cache" if contracts else "simulation"
    payload["contracts"] = contracts
    payload["contract_count"] = len(contracts)
    payload["cache_path"] = str(path)
    payload["cache_used"] = True
    payload.setdefault("error", "" if contracts else "cache empty")
    return payload


def xingyao_login():
    if not env_enabled("XINGYAO_ENABLED", "false"):
        raise RuntimeError("XINGYAO_ENABLED is false")
    username = os.getenv("XINGYAO_USER", "").strip()
    password = os.getenv("XINGYAO_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("missing credentials")
    add_xingyao_sdk_paths()
    import AmazingData as ad  # type: ignore

    host = os.getenv("XINGYAO_HOST", "101.230.159.234")
    port = int(os.getenv("XINGYAO_PORT", "8600"))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ok = ad.login(username=username, password=password, host=host, port=port)
    if not ok:
        raise RuntimeError("login failed")
    return ad


def dataframe_to_rows(value, max_rows: Optional[int] = None) -> List[Dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        rows = value.to_dict("records")
    elif isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = [value] if value else []
    else:
        rows = []
    if max_rows is not None:
        return rows[:max_rows]
    return rows


def xingyao_calendar(base) -> List[int]:
    calendar = []
    with contextlib.suppress(Exception):
        calendar = base.get_calendar()
    if not calendar:
        calendar = getattr(base, "calendar", []) or []
    return [int(item) for item in calendar if item]


def xingyao_market_result_to_rows(value, max_rows: Optional[int] = None, latest_only: bool = False) -> List[Dict]:
    if value is None:
        return []
    rows: List[Dict] = []

    if isinstance(value, dict):
        for outer_key, outer_value in value.items():
            if isinstance(outer_value, dict):
                for code, frame in outer_value.items():
                    frame_rows = dataframe_to_rows(frame)
                    if latest_only and frame_rows:
                        frame_rows = [frame_rows[-1]]
                    for row in frame_rows:
                        if isinstance(row, dict):
                            row.setdefault("date", outer_key)
                            row.setdefault("code", code)
                            rows.append(row)
            else:
                frame_rows = dataframe_to_rows(outer_value)
                if latest_only and frame_rows:
                    frame_rows = [frame_rows[-1]]
                for row in frame_rows:
                    if isinstance(row, dict):
                        row.setdefault("code", outer_key)
                        rows.append(row)
            if max_rows is not None and len(rows) >= max_rows:
                return rows[:max_rows]
        return rows[:max_rows] if max_rows is not None else rows

    return dataframe_to_rows(value, max_rows)


def xingyao_market_code(code: str) -> str:
    return f"{code}.SH" if market_prefix(code) == "1" else f"{code}.SZ"


def fetch_xingyao_snapshot_rows(codes: List[str]) -> Dict:
    """Read AmazingData market snapshots for ETF/A-share codes when permissions allow it."""
    if not codes:
        return {"enabled": False, "source": "xingyao_snapshot", "rows": [], "error": "empty codes"}
    try:
        ad = xingyao_login()
    except Exception as exc:
        return {"enabled": False, "source": "xingyao_snapshot", "rows": [], "error": str(exc)}

    try:
        base = ad.BaseData()
        calendar = xingyao_calendar(base)
        market = ad.MarketData(calendar)
        today = int(datetime.now(BEIJING_TZ).strftime("%Y%m%d"))
        sdk_codes = [xingyao_market_code(code) for code in codes]
        rows = market.query_snapshot(sdk_codes, today, today)
        records = xingyao_market_result_to_rows(rows, latest_only=True)
        return {
            "enabled": bool(records),
            "source": "xingyao_snapshot",
            "requested": sdk_codes,
            "calendar_len": len(calendar),
            "row_count": len(records),
            "rows": records,
            "error": "" if records else "empty snapshot",
        }
    except Exception as exc:
        return {"enabled": False, "source": "xingyao_snapshot", "rows": [], "error": str(exc)}
    finally:
        with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ad.logout()


def fetch_xingyao_kline_probe(codes: List[str]) -> Dict:
    return fetch_xingyao_kline_rows(codes[:3], days=1, max_rows=10, period="min1")


def fetch_xingyao_kline_rows(
    codes: List[str],
    days: int = 180,
    max_rows: Optional[int] = None,
    period: str = "day",
) -> Dict:
    """Read AmazingData K-line rows for ETF/A-share codes.

    period uses AmazingData constant names such as day/min1/min5.
    """
    try:
        ad = xingyao_login()
    except Exception as exc:
        return {"enabled": False, "source": "xingyao_kline", "rows": [], "error": str(exc)}

    try:
        base = ad.BaseData()
        calendar = xingyao_calendar(base)
        market = ad.MarketData(calendar)
        today = int(datetime.now(BEIJING_TZ).strftime("%Y%m%d"))
        begin = int((datetime.now(BEIJING_TZ) - timedelta(days=days)).strftime("%Y%m%d"))
        sdk_codes = [xingyao_market_code(code) for code in codes]
        query = getattr(market, "query_kline", None)
        if query is None:
            return {"enabled": False, "source": "xingyao_kline", "rows": [], "error": "AmazingData MarketData has no query_kline"}
        period_obj = getattr(getattr(ad, "constant", None), "Period", None)
        period_value = getattr(getattr(period_obj, period, None), "value", None)
        if period_value is None:
            raise RuntimeError(f"unsupported AmazingData period: {period}")
        rows = query(sdk_codes, begin, today, period=period_value)
        records = xingyao_market_result_to_rows(rows, max_rows)
        return {
            "enabled": bool(records),
            "source": "xingyao_kline",
            "requested": sdk_codes,
            "begin_date": begin,
            "end_date": today,
            "period": period,
            "calendar_len": len(calendar),
            "row_count": len(records),
            "rows": records,
            "error": "" if records else "empty kline",
        }
    except Exception as exc:
        return {"enabled": False, "source": "xingyao_kline", "rows": [], "error": str(exc)}
    finally:
        with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ad.logout()


def xingyao_sdk_capabilities() -> Dict:
    add_xingyao_sdk_paths()
    capabilities = {
        "sdk_paths": [path for path in xingyao_sdk_paths() if path],
        "amazingdata_import": False,
        "tgw_import": False,
        "amazingdata_methods": {},
        "tgw_methods": [],
        "sdk_error": "",
    }
    try:
        import AmazingData as ad  # type: ignore

        capabilities["amazingdata_import"] = True
        for class_name in ("BaseData", "InfoData", "MarketData"):
            cls = getattr(ad, class_name, None)
            capabilities["amazingdata_methods"][class_name] = [
                item for item in dir(cls) if cls is not None and not item.startswith("_")
            ]
    except Exception as exc:
        capabilities["sdk_error"] = f"AmazingData import failed: {exc}"

    try:
        from tgw import interface as tgw_interface  # type: ignore

        capabilities["tgw_import"] = True
        capabilities["tgw_methods"] = [
            item
            for item in (
                "QuerySnapshot",
                "QueryKline",
                "QuerySecuritiesInfo",
                "QueryETFInfo",
                "Subscribe",
            )
            if hasattr(tgw_interface, item)
        ]
    except Exception as exc:
        if capabilities["sdk_error"]:
            capabilities["sdk_error"] += f"; TGW import failed: {exc}"
        else:
            capabilities["sdk_error"] = f"TGW import failed: {exc}"

    return capabilities


def run_xingyao_data_diagnostics(option_radar: Optional[Dict] = None) -> Dict:
    """Summarize how much of Galaxy Xingyao/AmazingData is actually usable today."""
    sample_codes = [
        code.strip()
        for code in os.getenv("XINGYAO_PROBE_CODES", "510300,588000,512100,510050,600498").split(",")
        if code.strip()
    ]
    capabilities = xingyao_sdk_capabilities()
    option_status = option_radar if (option_radar or {}).get("contract_count", 0) else None
    if not option_status:
        option_status = load_xingyao_option_cache() or fetch_xingyao_option_basic_rows()
    snapshot_status = fetch_xingyao_snapshot_rows(sample_codes)
    kline_status = fetch_xingyao_kline_probe(sample_codes) if env_enabled("XINGYAO_KLINE_PROBE_ENABLED", "false") else {
        "enabled": False,
        "source": "xingyao_kline",
        "row_count": 0,
        "error": "disabled by XINGYAO_KLINE_PROBE_ENABLED=false",
    }

    matrix = [
        {
            "module": "期权基础合约",
            "sdk_api": "BaseData.get_option_code_list + InfoData.get_option_basic_info",
            "status": "OK" if option_status.get("contract_count", 0) else "FALLBACK",
            "rows": option_status.get("contract_count", 0),
            "note": option_status.get("error", "") or (
                "已接入，可用于合约匹配；不是实时盘口。"
                if option_status.get("contract_count", 0)
                else "未读取到期权基础合约；期权只能保留模拟估算。"
            ),
        },
        {
            "module": "ETF/A股实时快照",
            "sdk_api": "MarketData.query_snapshot / TGW QuerySnapshot",
            "status": "OK" if snapshot_status.get("row_count", 0) else "NOT_READY",
            "rows": snapshot_status.get("row_count", 0),
            "note": snapshot_status.get("error", "") or "可作为主行情候选源。",
        },
        {
            "module": "K线",
            "sdk_api": "MarketData.query_kline / TGW QueryKline",
            "status": "OK" if kline_status.get("row_count", 0) else "NOT_READY",
            "rows": kline_status.get("row_count", 0),
            "note": kline_status.get("error", "") or "可用于均线/回测。",
        },
        {
            "module": "期权实时快照",
            "sdk_api": "TGWOptionSnapshot / QuerySnapshot",
            "status": "PENDING",
            "rows": 0,
            "note": "已在SDK结构中看到能力；需用银河账号权限继续验证真实权利金、成交量、持仓量、IV/希腊值字段。",
        },
    ]

    active_sources = []
    if option_status.get("contract_count", 0):
        active_sources.append("xingyao_option_basic")
    if snapshot_status.get("row_count", 0):
        active_sources.append("xingyao_snapshot")
    if kline_status.get("row_count", 0):
        active_sources.append("xingyao_kline")

    return {
        "enabled": env_enabled("XINGYAO_ENABLED", "false"),
        "quote_priority_enabled": env_enabled("XINGYAO_QUOTE_PRIORITY", "false"),
        "sample_codes": sample_codes,
        "active_sources": active_sources,
        "capabilities": capabilities,
        "option_basic": {
            "source": option_status.get("source", ""),
            "contract_count": option_status.get("contract_count", 0),
            "cache_used": option_status.get("cache_used", False),
            "cache_updated_at": option_status.get("cache_updated_at", ""),
            "error": option_status.get("error", ""),
        },
        "snapshot_probe": {
            "source": snapshot_status.get("source", ""),
            "requested": snapshot_status.get("requested", []),
            "row_count": snapshot_status.get("row_count", 0),
            "sample_rows": dataframe_to_rows(snapshot_status.get("rows", []), 5),
            "error": snapshot_status.get("error", ""),
        },
        "kline_probe": {
            "source": kline_status.get("source", ""),
            "requested": kline_status.get("requested", []),
            "row_count": kline_status.get("row_count", 0),
            "sample_rows": dataframe_to_rows(kline_status.get("rows", []), 5),
            "error": kline_status.get("error", ""),
        },
        "matrix": matrix,
        "recommendation": (
            "星耀快照已可用，可把星耀作为主行情源。"
            if snapshot_status.get("row_count", 0)
            else "星耀SDK能力存在，但实时快照未返回数据；先保留东方财富/新浪/腾讯兜底，向银河确认快照/K线/期权实时权限。"
        ),
    }


def fetch_xingyao_option_basic_rows() -> Dict:
    """Fetch ETF option basic info from Galaxy AmazingData when configured locally."""
    cached_before_fetch = load_xingyao_option_cache()
    if not env_enabled("XINGYAO_ENABLED", "false"):
        if cached_before_fetch and cached_before_fetch.get("contracts"):
            return cached_before_fetch
        return {"enabled": False, "source": "simulation", "contracts": [], "error": "disabled; no local cache"}

    username = os.getenv("XINGYAO_USER", "").strip()
    password = os.getenv("XINGYAO_PASSWORD", "").strip()
    if not username or not password:
        if cached_before_fetch and cached_before_fetch.get("contracts"):
            cached_before_fetch["error"] = "using cache; missing credentials"
            return cached_before_fetch
        return {"enabled": False, "source": "simulation", "contracts": [], "error": "missing credentials; no local cache"}

    try:
        ad = xingyao_login()
    except Exception as exc:
        return {"enabled": False, "source": "simulation", "contracts": [], "error": f"import failed: {exc}"}

    try:
        base = ad.BaseData()
        info = ad.InfoData()
        option_codes = base.get_option_code_list("EXTRA_ETF_OP")
        option_info = info.get_option_basic_info(option_codes, is_local=False)
        contracts = option_info.to_dict("records") if hasattr(option_info, "to_dict") else []
        cached_count = int((cached_before_fetch or {}).get("contract_count") or 0)
        if cached_count >= 1000 and len(contracts) < cached_count * 0.8:
            cached_before_fetch["error"] = f"using cache; live fetch returned narrow result {len(contracts)}/{len(option_codes)}"
            return cached_before_fetch
        payload = {
            "enabled": True,
            "source": "xingyao_basic",
            "contracts": contracts,
            "contract_count": len(contracts),
            "option_code_count": len(option_codes),
            "error": "",
        }
        save_xingyao_option_cache(payload)
        return payload
    except Exception as exc:
        logger.warning("Xingyao option basic fetch failed: %s", exc)
        cached = load_xingyao_option_cache()
        if cached and cached.get("contracts"):
            cached["error"] = f"using cache; live fetch failed: {exc}"
            return cached
        return {"enabled": False, "source": "simulation", "contracts": [], "error": str(exc)}
    finally:
        with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ad.logout()


def xingyao_contract_for(option_rows: List[Dict], etf_code: str, direction: str, strike: float, expiry: str) -> Optional[Dict]:
    contract_type = "C" if direction == "认购" else "P"
    expiry_key = expiry.replace("-", "")[:6]
    candidates = []
    tolerance = max(option_strike_step(strike) / 2, 0.001)
    for row in option_rows:
        exchange_code = str(row.get("EXCHANGE_CODE", ""))
        if not exchange_code.startswith(etf_code):
            continue
        if str(row.get("CONTRACT_TYPE", "")).upper() != contract_type:
            continue
        if str(row.get("DELIVERY_MONTH", "")) != expiry_key:
            continue
        try:
            row_strike = float(row.get("EXERCISE_PRICE"))
        except (TypeError, ValueError):
            continue
        diff = abs(row_strike - strike)
        if diff > tolerance:
            continue
        candidates.append((diff, row))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def run_option_sim_radar() -> Dict:
    if not env_enabled("OPTION_SIM_RADAR_ENABLED", "true"):
        return {"enabled": False, "results": [], "failures": []}

    now = datetime.now(BEIJING_TZ)
    expiry = next_option_expiry(now)
    days_to_expiry = max((expiry.date() - now.date()).days, 1)
    results = []
    failures = []
    xingyao = fetch_xingyao_option_basic_rows()
    xingyao_rows = xingyao.get("contracts", [])

    for code in load_option_etf_watchlist():
        try:
            quote = fetch_quote(code)
            if not quote.price:
                raise ValueError("missing ETF price")
            strike = nearest_option_strike(quote.price)
            for direction in ("认购", "认沽"):
                xingyao_contract = xingyao_contract_for(
                    xingyao_rows,
                    code,
                    direction,
                    strike,
                    expiry.strftime("%Y-%m-%d"),
                )
                premium = estimate_option_premium(quote.price, days_to_expiry, direction)
                break_even = strike + premium if direction == "认购" else strike - premium
                if quote.pct_change is None:
                    suitability = "只观察：缺少当日涨跌幅"
                elif direction == "认购" and 0.4 <= quote.pct_change <= 3.5:
                    suitability = "可模拟认购：方向偏强，但只用仿真盘验证"
                elif direction == "认沽" and quote.pct_change <= -0.8:
                    suitability = "可模拟认沽：方向偏弱，但只用仿真盘验证"
                else:
                    suitability = "不适合主动模拟：方向或赔率不清晰"
                results.append(
                    {
                        "code": code,
                        "name": quote.name,
                        "etf_price": quote.price,
                        "pct_change": quote.pct_change,
                        "direction": direction,
                        "strike": strike,
                        "expiry": expiry.strftime("%Y-%m-%d"),
                        "days_to_expiry": days_to_expiry,
                        "premium": premium,
                        "contract_cost": premium * 10000,
                        "break_even": break_even,
                        "max_loss": premium * 10000,
                        "time_risk": option_time_risk(days_to_expiry, premium),
                        "suitability": suitability,
                        "xingyao_contract_code": (xingyao_contract or {}).get("EXCHANGE_CODE"),
                        "xingyao_contract_name": (xingyao_contract or {}).get("CONTRACT_FULL_NAME"),
                        "xingyao_listing_ref_price": safe_float((xingyao_contract or {}).get("LISTING_REF_PRICE")),
                        "scenarios": [
                            option_payoff(quote.price, strike, premium, direction, move)
                            for move in (-3, -2, -1, 1, 2, 3)
                        ],
                        "quote_note": "权利金为模拟估算，不是真实期权链报价；接入银河仿真盘后再替换为真实权利金/隐含波动率/希腊值。",
                    }
                )
        except Exception as exc:
            logger.warning("option sim ETF %s skipped: %s", code, exc)
            failures.append({"code": code, "error": str(exc)})

    return {
        "enabled": True,
        "watch_count": len(load_option_etf_watchlist()),
        "expiry": expiry.strftime("%Y-%m-%d"),
        "days_to_expiry": days_to_expiry,
        "contract_multiplier": 10000,
        "data_source": xingyao.get("source", "simulation"),
        "xingyao_enabled": xingyao.get("enabled", False),
        "xingyao_contract_count": xingyao.get("contract_count", 0),
        "xingyao_error": xingyao.get("error", ""),
        "xingyao_cache_used": xingyao.get("cache_used", False),
        "xingyao_cache_path": xingyao.get("cache_path", ""),
        "xingyao_cache_updated_at": xingyao.get("cache_updated_at", ""),
        "results": results,
        "failures": failures,
    }


def fetch_realtime_quote(code: str) -> Quote:
    """Fetch a lightweight quote without moving averages for wider stock scans."""
    data = eastmoney_get(
        "https://push2.eastmoney.com/api/qt/stock/get",
        {
            "secid": secid(code),
            "fields": "f57,f58,f43,f170,f48",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        },
        timeout=10,
    ).get("data") or {}

    name = data.get("f58") or code
    price = eastmoney_price_float(code, data.get("f43"))
    pct_change = safe_float(data.get("f170"), 100)
    amount = safe_float(data.get("f48"), 1)

    if price is None:
        raise ValueError("missing price")

    ma20, ma60 = (None, None)
    if code in focus_stock_codes() and env_enabled("AI_STOCK_FOCUS_MA_ENABLED", "true"):
        ma20, ma60 = fetch_moving_averages(code)

    return Quote(
        code=code,
        name=name,
        price=price,
        pct_change=pct_change,
        amount=amount,
        ma20=ma20,
        ma60=ma60,
    )


def market_scan_allowed_prefixes() -> tuple:
    raw = os.getenv(
        "BROAD_MARKET_ALLOWED_PREFIXES",
        "000,001,002,003,300,301,600,601,603,605,688,689,830,831,832,833,834,835,836,837,838,839,870,871,872,873,920",
    )
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def board_label(code: str) -> str:
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith(("8", "920")):
        return "北交所"
    if code.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "沪深主板"
    return "其他"


def is_tradeable_a_share_code(code: str, name: str) -> bool:
    if not code.startswith(market_scan_allowed_prefixes()):
        return False
    blocked_name_tokens = ("ST", "*ST", "退", "N", "C")
    return not any(token in name for token in blocked_name_tokens)


def fetch_market_snapshot_page(page: int, page_size: int = 100) -> List[Dict]:
    data = eastmoney_get(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": page,
            "pz": page_size,
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": "f6",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f2,f3,f6,f8,f10,f17,f18,f100",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        },
        timeout=int(os.getenv("BROAD_MARKET_PAGE_TIMEOUT_SECONDS", "2")),
        retries=int(os.getenv("BROAD_MARKET_PAGE_RETRIES", "1")),
    ).get("data") or {}
    return data.get("diff") or []


def sina_market_node() -> str:
    return os.getenv("SINA_MARKET_NODE", "hs_a").strip() or "hs_a"


def parse_sina_market_rows(text: str) -> List[Dict]:
    rows = []
    try:
        payload = json.loads(text or "[]")
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, list):
        for values in payload:
            if not isinstance(values, dict):
                continue
            symbol = str(values.get("symbol") or "")
            code = str(values.get("code") or symbol[-6:])
            if not code or len(code) != 6:
                continue
            rows.append(
                {
                    "f12": code,
                    "f14": values.get("name") or code,
                    "f2": values.get("trade") or values.get("price"),
                    "f3": values.get("changepercent"),
                    "f6": values.get("amount"),
                    "f8": values.get("turnoverratio"),
                    "f10": None,
                    "f17": values.get("open"),
                    "f18": values.get("settlement"),
                    "f100": values.get("industry") or "",
                    "source": "sina",
                }
            )
        return rows

    for match in re.finditer(r"\{([^{}]+)\}", text or ""):
        raw = match.group(1)
        values = {}
        for item in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*):(?:\"([^\"]*)\"|([^,}]+))", raw):
            key = item.group(1)
            value = item.group(2) if item.group(2) is not None else item.group(3)
            values[key] = str(value).strip()

        symbol = values.get("symbol") or ""
        code = values.get("code") or symbol[-6:]
        if not code or len(code) != 6:
            continue

        rows.append(
            {
                "f12": code,
                "f14": values.get("name") or code,
                "f2": values.get("trade") or values.get("price"),
                "f3": values.get("changepercent"),
                "f6": values.get("amount"),
                "f8": values.get("turnoverratio"),
                "f10": None,
                "f17": values.get("open"),
                "f18": values.get("settlement"),
                "f100": values.get("industry") or "",
                "source": "sina",
            }
        )
    return rows


def fetch_market_snapshot_page_sina(page: int, page_size: int = 100) -> List[Dict]:
    response = requests.get(
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        params={
            "page": page,
            "num": min(page_size, int(os.getenv("SINA_MARKET_PAGE_SIZE", "200"))),
            "sort": "amount",
            "asc": "0",
            "node": sina_market_node(),
            "symbol": "",
            "_s_r_a": "init",
        },
        headers={
            "User-Agent": "Mozilla/5.0 ETF Strategy Monitor",
            "Referer": "https://vip.stock.finance.sina.com.cn/",
        },
        timeout=int(os.getenv("SINA_MARKET_PAGE_TIMEOUT_SECONDS", "3")),
    )
    response.raise_for_status()
    response.encoding = "gbk"
    return parse_sina_market_rows(response.text)


def fetch_market_snapshot_page_with_fallback(page: int, page_size: int = 100) -> tuple:
    sources = [item.strip().lower() for item in os.getenv("BROAD_MARKET_SOURCES", "eastmoney,sina").split(",") if item.strip()]
    errors = []
    for source in sources:
        try:
            if source == "eastmoney":
                rows = fetch_market_snapshot_page(page, page_size)
            elif source == "sina":
                rows = fetch_market_snapshot_page_sina(page, page_size)
            else:
                errors.append(f"{source}: unsupported broad-market source")
                continue
            if rows:
                return rows, source, errors
            errors.append(f"{source}: empty page")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    raise RuntimeError("; ".join(errors) or "all broad-market sources failed")


def fetch_market_snapshot_page_from_source(source: str, page: int, page_size: int = 100) -> List[Dict]:
    source = source.strip().lower()
    if source == "eastmoney":
        return fetch_market_snapshot_page(page, page_size)
    if source == "sina":
        return fetch_market_snapshot_page_sina(page, page_size)
    raise RuntimeError(f"{source}: unsupported broad-market source")


def layer_index_from_watchlist(watchlist: Dict) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for layer in watchlist.get("layers") or []:
        layer_name = layer.get("name") or ""
        for code in layer.get("codes", []):
            code = str(code).strip()
            if code:
                index.setdefault(code, []).append(layer_name)
    return index


def classify_market_candidate(row: Dict, layer_index: Dict[str, List[str]]) -> Optional[Dict]:
    code = str(row.get("f12") or "").strip()
    name = str(row.get("f14") or code).strip()
    if not code or not is_tradeable_a_share_code(code, name):
        return None

    price = safe_float(row.get("f2"))
    pct = safe_float(row.get("f3"))
    amount = safe_float(row.get("f6"))
    turnover = safe_float(row.get("f8"))
    volume_ratio = safe_float(row.get("f10"))
    open_price = safe_float(row.get("f17"))
    prev_close = safe_float(row.get("f18"))
    industry = str(row.get("f100") or "").strip()
    board = board_label(code)
    data_source = str(row.get("_source") or row.get("source") or "unknown").strip().lower()
    data_quality = "full" if volume_ratio is not None and turnover is not None and industry else "partial"

    if price is None or pct is None or amount is None:
        return None

    min_amount = float(os.getenv("BROAD_MARKET_MIN_AMOUNT", "300000000"))
    min_pct = float(os.getenv("BROAD_MARKET_MIN_PCT", "1.2"))
    max_pct = float(os.getenv("BROAD_MARKET_MAX_PCT", "6.2"))
    min_turnover = float(os.getenv("BROAD_MARKET_MIN_TURNOVER", "0.5"))
    max_turnover = float(os.getenv("BROAD_MARKET_MAX_TURNOVER", "18"))
    min_volume_ratio = float(os.getenv("BROAD_MARKET_MIN_VOLUME_RATIO", "1.0"))

    if amount < min_amount:
        return None
    if pct < min_pct or pct > max_pct:
        return None
    if turnover is not None and (turnover < min_turnover or turnover > max_turnover):
        return None
    if volume_ratio is not None and volume_ratio < min_volume_ratio:
        return None

    theme_layers = layer_index.get(code, [])
    theme_bonus = 2.0 if theme_layers else -0.8
    open_strength = 0.0
    if open_price and prev_close and open_price > prev_close:
        open_strength = min(((open_price / prev_close) - 1) * 100, 3.0)

    intraday_pct = None
    intraday_component = 0.0
    if price and open_price:
        intraday_pct = (price / open_price - 1) * 100
        if pct > 0 and intraday_pct >= 0.4:
            intraday_component = 0.8
        elif pct > 0 and intraday_pct <= -1.2:
            intraday_component = -1.8
        elif pct > 0 and -0.5 <= intraday_pct <= 0.4:
            intraday_component = 0.2

    turnover_component = 0.0
    if turnover is not None:
        if 3 <= turnover <= 12:
            turnover_component = 1.2
        elif turnover > 15:
            turnover_component = -1.2
        elif turnover < 1:
            turnover_component = -0.6

    score = (
        pct * 1.2
        + min(log10(max(amount, 1) / 100_000_000), 2.0) * 2.0
        + min(volume_ratio or 0, 4.0)
        + min(turnover or 0, 8.0) * 0.15
        + open_strength * 0.4
        + intraday_component
        + turnover_component
        + theme_bonus
    )
    if pct >= 5.5:
        score -= 1.5

    reasons = [
        f"涨幅 {pct:.2f}%，未超过追高过滤线",
        f"成交额 {amount / 100_000_000:.1f}亿",
    ]
    if volume_ratio is not None:
        reasons.append(f"量比 {volume_ratio:.2f}")
    if turnover is not None:
        reasons.append(f"换手 {turnover:.2f}%")
    if intraday_pct is not None:
        if intraday_pct >= 0.4:
            reasons.append(f"开盘后仍上涨 {intraday_pct:.2f}%，承接较好")
        elif intraday_pct <= -1.2:
            reasons.append(f"开盘后回落 {intraday_pct:.2f}%，可能是高开回落，不急买")
        else:
            reasons.append(f"开盘后变化 {intraday_pct:.2f}%，等待9:40确认")
    if theme_layers:
        reasons.append("命中主题层：" + " / ".join(theme_layers[:2]))
    else:
        reasons.append("未命中当前AI/数字基建主线，降级为全市场异动")
    if industry:
        reasons.append(f"行业：{industry}")
    if data_quality != "full":
        reasons.append("备用源字段不完整：只进观察池，不直接进入今日可操作池")

    return {
        "code": code,
        "name": name,
        "board": board,
        "price": price,
        "pct_change": pct,
        "amount": amount,
        "turnover": turnover,
        "volume_ratio": volume_ratio,
        "intraday_pct": intraday_pct,
        "industry": industry,
        "theme_layers": theme_layers,
        "data_source": data_source,
        "data_quality": data_quality,
        "score": score,
        "action": "候选，等回踩/二次确认",
        "reasons": reasons,
    }


def run_broad_market_scan(watchlist: Dict) -> Dict:
    if not env_enabled("BROAD_MARKET_SCAN_ENABLED", "true"):
        return {"enabled": False, "results": [], "failures": []}

    max_pages = int(os.getenv("BROAD_MARKET_MAX_PAGES", "60"))
    page_size = int(os.getenv("BROAD_MARKET_PAGE_SIZE", "100"))
    min_rows = int(os.getenv("BROAD_MARKET_MIN_ROWS", "5000"))
    time_budget = float(os.getenv("BROAD_MARKET_TIME_BUDGET_SECONDS", "110"))
    layer_index = layer_index_from_watchlist(watchlist)
    candidates = []
    failures = []
    source_counts = {}
    raw_seen_codes = set()
    seen_codes = set()
    total_rows_seen = 0
    started_at = time.monotonic()
    sources = [item.strip().lower() for item in os.getenv("BROAD_MARKET_SOURCES", "eastmoney,sina").split(",") if item.strip()]

    for source in sources:
        empty_pages = 0
        for page in range(1, max_pages + 1):
            elapsed = time.monotonic() - started_at
            if elapsed >= time_budget:
                failures.append({"page": page, "source": source, "error": f"broad market scan time budget reached after {elapsed:.1f}s"})
                break
            try:
                rows = fetch_market_snapshot_page_from_source(source, page, page_size)
                if not rows:
                    empty_pages += 1
                    failures.append({"page": page, "source": source, "error": "empty page"})
                    if empty_pages >= 2:
                        break
                    continue
                source_counts[source] = source_counts.get(source, 0) + len(rows)
                for row in rows:
                    code = str(row.get("f12") or row.get("code") or "").strip()
                    if code and code not in raw_seen_codes:
                        raw_seen_codes.add(code)
                        total_rows_seen += 1
                    row_with_source = dict(row)
                    row_with_source["_source"] = source
                    item = classify_market_candidate(row_with_source, layer_index)
                    if not item or item["code"] in seen_codes:
                        continue
                    seen_codes.add(item["code"])
                    candidates.append(item)
            except Exception as exc:
                logger.warning("broad market page %s from %s skipped: %s", page, source, exc)
                failures.append({"page": page, "source": source, "error": str(exc)})
                hard_failures = [item for item in failures if item.get("error") != "empty page"]
                if len(hard_failures) >= 6:
                    break
        if total_rows_seen >= min_rows:
            break
        if time.monotonic() - started_at >= time_budget:
            break

    if total_rows_seen < min_rows and len(sources) <= 1:
        for page in range(1, max_pages + 1):
            elapsed = time.monotonic() - started_at
            if elapsed >= time_budget:
                failures.append({"page": page, "source": "fallback", "error": f"broad market scan time budget reached after {elapsed:.1f}s"})
                break
            try:
                rows, source, source_errors = fetch_market_snapshot_page_with_fallback(page, page_size)
                for source_error in source_errors:
                    failures.append({"page": page, "source": "fallback", "error": source_error})
                if not rows:
                    break
                source_counts[source] = source_counts.get(source, 0) + len(rows)
                for row in rows:
                    code = str(row.get("f12") or row.get("code") or "").strip()
                    if code and code not in raw_seen_codes:
                        raw_seen_codes.add(code)
                        total_rows_seen += 1
                    row_with_source = dict(row)
                    row_with_source["_source"] = source
                    item = classify_market_candidate(row_with_source, layer_index)
                    if not item or item["code"] in seen_codes:
                        continue
                    seen_codes.add(item["code"])
                    candidates.append(item)
            except Exception as exc:
                logger.warning("broad market fallback page %s skipped: %s", page, exc)
                failures.append({"page": page, "source": "fallback", "error": str(exc)})

    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    max_results = int(os.getenv("BROAD_MARKET_MAX_RESULTS", "50"))
    capacity = max_pages * page_size
    return {
        "enabled": True,
        "scan_pages": max_pages,
        "page_size": page_size,
        "min_rows_target": min_rows,
        "sources": sources,
        "source_counts": source_counts,
        "scanned_count": total_rows_seen,
        "missing_estimate": max(min_rows - total_rows_seen, 0),
        "scan_capacity": max_pages * page_size * max(len(sources), 1),
        "candidate_count": len(seen_codes),
        "results": candidates[:max_results],
        "failures": failures,
    }


def fetch_moving_averages(code: str) -> tuple:
    try:
        data = eastmoney_get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            {
                "secid": secid(code),
                "klt": 101,
                "fqt": 1,
                "lmt": 80,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            },
            timeout=int(os.getenv("EASTMONEY_KLINE_TIMEOUT_SECONDS", "8")),
            retries=int(os.getenv("EASTMONEY_KLINE_RETRIES", "2")),
            warn=False,
        ).get("data") or {}
        klines = data.get("klines") or []
        closes = [float(item.split(",")[2]) for item in klines if len(item.split(",")) > 2]
        ma20 = mean(closes[-20:]) if len(closes) >= 20 else None
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else None
        return ma20, ma60
    except Exception as exc:
        logger.info("Moving averages unavailable for %s: %s", code, exc)
        return None, None


def focus_stock_codes() -> set:
    raw = os.getenv(
        "AI_STOCK_FOCUS_CODES",
        "688041,688047,000066,603019,002156,688981,688012,300308,300502,300394,000063,"
        "601728,600498,300054,002747,002472,300124,688017,002085,000099,688297,601698,600118,300045,"
        "688111,300033,688808,603986,002371,688072,688120,002409,600584,000021,000032",
    )
    return {code.strip() for code in raw.split(",") if code.strip()}


def classify_quote(quote: Quote, high_risk_codes: set, qdii_codes: set) -> Dict:
    reasons = []
    action = "观察，不追"
    level = "YELLOW"

    price = quote.price
    pct = quote.pct_change
    ma20 = quote.ma20
    ma60 = quote.ma60

    if quote.code in high_risk_codes:
        level = "RED"
        action = "禁止追买"
        reasons.append("高溢价/停牌风险样本，先等情绪降温")

    if quote.premium is not None:
        if quote.premium > 5:
            level = "RED"
            action = "禁止追买"
            reasons.append(f"溢价 {quote.premium:.2f}% > 5%")
        elif quote.premium >= 2:
            reasons.append(f"溢价 {quote.premium:.2f}%，只能小仓观察")

    if pct is not None:
        if pct >= 7:
            level = "RED"
            action = "禁止追买"
            reasons.append(f"单日涨幅 {pct:.2f}%，短线过热")
        elif pct >= 3:
            if level != "RED":
                level = "YELLOW"
            reasons.append(f"单日涨幅 {pct:.2f}%，不追高")
        elif pct <= -4 and level != "RED":
            reasons.append(f"单日回撤 {pct:.2f}%，只按计划分批")

    trend_ok = False
    if price and ma20 and ma60:
        if price > ma20 > ma60:
            trend_ok = True
            reasons.append("价格站上20/60日均线，趋势偏强")
        elif price < ma20 and level != "RED":
            level = "YELLOW"
            reasons.append("价格低于20日线，等待企稳")
        elif ma20 < ma60 and level != "RED":
            level = "YELLOW"
            reasons.append("20日线低于60日线，趋势未修复")

    if level != "RED" and trend_ok and (pct is None or pct < 3):
        level = "GREEN"
        action = "可研究小仓/按网格执行"

    if quote.code in qdii_codes:
        reasons.append("QDII标的需额外看IOPV/溢价，溢价高时不买")

    if not reasons:
        reasons.append("数据正常，但没有明显强信号")

    return {
        "code": quote.code,
        "name": quote.name,
        "price": quote.price,
        "pct_change": quote.pct_change,
        "amount": quote.amount,
        "ma20": quote.ma20,
        "ma60": quote.ma60,
        "premium": quote.premium,
        "level": level,
        "action": action,
        "reasons": reasons,
    }


def load_watchlist() -> List[str]:
    raw = os.getenv("ETF_WATCHLIST", "")
    if not raw:
        return DEFAULT_WATCHLIST
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_portfolio() -> Dict:
    try:
        data = load_json_file(PORTFOLIO_FILE)
    except FileNotFoundError:
        logger.info(
            "No portfolio config found at %s. Copy portfolio.example.json to portfolio.local.json "
            "or set PORTFOLIO_FILE to enable portfolio-aware actions.",
            PORTFOLIO_FILE,
        )
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid portfolio config, strategy actions will be skipped: %s", exc)
        return {}

    data.setdefault("positions", [])
    data.setdefault("total_capital", 0)
    data.setdefault("cash", 0)
    data.setdefault("max_single_weight", 0.25)
    data.setdefault("default_buy_amount", 10000)
    return data


def load_digital_infra_watchlist() -> Dict:
    try:
        return load_json_file(DIGITAL_INFRA_FILE)
    except FileNotFoundError:
        logger.info("No digital infra watchlist found, stock radar will be skipped")
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid digital infra watchlist, stock radar will be skipped: %s", exc)
        return {}


def watched_codes_from_portfolio(portfolio: Dict) -> List[str]:
    return [
        str(item.get("code", "")).strip()
        for item in portfolio.get("positions", [])
        if str(item.get("code", "")).strip()
    ]


def combined_watchlist() -> List[str]:
    codes = []
    for code in load_watchlist() + watched_codes_from_portfolio(load_portfolio()):
        if code not in codes:
            codes.append(code)
    return codes


def coverage_report(
    watchlist: List[str],
    stock_radar: Dict,
    broad_market_scan: Dict,
    option_sim_radar: Dict,
    xingyao_data_status: Optional[Dict] = None,
) -> Dict:
    max_pages = int(os.getenv("BROAD_MARKET_MAX_PAGES", "60"))
    page_size = int(os.getenv("BROAD_MARKET_PAGE_SIZE", "100"))
    allowed_prefixes = list(market_scan_allowed_prefixes())
    return {
        "etf_watch_count": len(watchlist),
        "etf_watchlist": watchlist,
        "option_etf_watchlist": load_option_etf_watchlist(),
        "option_rows": len(option_sim_radar.get("results", [])),
        "ai_stock_watch_count": stock_radar.get("watch_count", 0),
        "broad_scan_enabled": broad_market_scan.get("enabled", False),
        "broad_scan_pages_budget": max_pages,
        "broad_scan_page_size": page_size,
        "broad_scan_capacity": broad_market_scan.get("scan_capacity", max_pages * page_size),
        "broad_scan_min_rows_target": broad_market_scan.get("min_rows_target", int(os.getenv("BROAD_MARKET_MIN_ROWS", "5000"))),
        "broad_scan_sources": broad_market_scan.get("sources", []),
        "broad_source_counts": broad_market_scan.get("source_counts", {}),
        "broad_rows_seen": broad_market_scan.get("scanned_count", 0),
        "broad_missing_estimate": broad_market_scan.get("missing_estimate", 0),
        "broad_candidates": broad_market_scan.get("candidate_count", 0),
        "xingyao_active_sources": (xingyao_data_status or {}).get("active_sources", []),
        "xingyao_snapshot_rows": ((xingyao_data_status or {}).get("snapshot_probe") or {}).get("row_count", 0),
        "xingyao_kline_rows": ((xingyao_data_status or {}).get("kline_probe") or {}).get("row_count", 0),
        "xingyao_recommendation": (xingyao_data_status or {}).get("recommendation", ""),
        "allowed_prefixes": allowed_prefixes,
        "coverage_note": "ETF为重点监控池；A股扫描覆盖沪深主板、创业板、科创板、北交所常见代码前缀，并过滤ST/新股/退市风险；创业板/科创板/北交所只做观察提示，默认不直接下单。",
    }


def position_map(portfolio: Dict) -> Dict[str, Dict]:
    return {str(item.get("code")): item for item in portfolio.get("positions", [])}


def digital_infra_layers(watchlist: Dict) -> List[Dict]:
    layers = watchlist.get("layers") or []
    focus_raw = os.getenv("AI_STOCK_FOCUS_LAYERS", "")
    focus_layers = [item.strip() for item in focus_raw.split(",") if item.strip()]
    if not focus_layers:
        focus_layers = watchlist.get("focus_layers") or []
    if not focus_layers:
        return layers
    focus_set = set(focus_layers)
    return [layer for layer in layers if layer.get("id") in focus_set]


def classify_stock_quote(quote: Quote, layer: Dict) -> Dict:
    reasons = []
    level = "YELLOW"
    action = "观察，不追"
    pct = quote.pct_change
    price = quote.price
    ma20 = quote.ma20
    ma60 = quote.ma60

    if price and ma20 and ma60 and price > ma20 > ma60:
        level = "GREEN"
        action = "可列入卫星仓候选"
        reasons.append("价格站上20/60日线，趋势结构较强")
    elif price and ma20 and price < ma20:
        reasons.append("价格低于20日线，等待趋势修复")

    if pct is not None:
        if pct >= 10:
            level = "RED"
            action = "禁止追买"
            reasons.append(f"单日涨幅 {pct:.2f}%，疑似情绪过热")
        elif pct >= 5:
            if level != "RED":
                level = "YELLOW"
                action = "强势观察，不追"
            reasons.append(f"单日涨幅 {pct:.2f}%，先等回踩或二次确认")
        elif pct <= -5:
            reasons.append(f"单日回撤 {pct:.2f}%，只观察承接")

    if quote.amount and quote.amount > 1_000_000_000:
        reasons.append("成交额放大，资金关注度提高")

    layer_name = layer.get("name", "")
    if "存算" in layer_name or "存储" in layer_name:
        reasons.append("AI存储/存算方向，重点看涨价、订单和量产验证")
    elif "光" in layer_name or "CPO" in layer_name:
        reasons.append("AI高速互联方向，重点看订单、速率迭代和海外链确认")
    elif "芯片" in layer_name:
        reasons.append("AI芯片方向弹性高，估值和情绪波动也高")

    return {
        "code": quote.code,
        "name": quote.name,
        "layer_id": layer.get("id"),
        "layer_name": layer_name,
        "layer_logic": layer.get("logic", ""),
        "price": quote.price,
        "pct_change": quote.pct_change,
        "amount": quote.amount,
        "ma20": quote.ma20,
        "ma60": quote.ma60,
        "level": level,
        "action": action,
        "reasons": reasons or ["暂无强信号，保留观察"],
    }


def run_stock_radar() -> Dict:
    if not env_enabled("AI_STOCK_RADAR_ENABLED", "true"):
        return {"enabled": False, "watch_count": 0, "results": [], "failures": [], "layers": []}

    watchlist = load_digital_infra_watchlist()
    layers = digital_infra_layers(watchlist)
    max_codes = int(os.getenv("AI_STOCK_MAX_CODES", "240"))
    results = []
    failures = []
    seen_codes = set()

    for layer in layers:
        for code in layer.get("codes", []):
            code = str(code).strip()
            if not code or code in seen_codes:
                continue
            if len(seen_codes) >= max_codes:
                break
            seen_codes.add(code)
            try:
                quote = fetch_realtime_quote(code)
                item = classify_stock_quote(quote, layer)
                results.append(item)
                logger.info("stock %s %s checked", code, quote.name)
            except Exception as exc:
                logger.warning("stock %s skipped: %s", code, exc)
                failures.append({"code": code, "layer": layer.get("name"), "error": str(exc)})
        if len(seen_codes) >= max_codes:
            break

    results.sort(
        key=lambda item: (
            {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(item.get("level"), 3),
            -(item.get("pct_change") or -999),
        )
    )
    return {
        "enabled": True,
        "watch_count": len(seen_codes),
        "layers": [{"id": layer.get("id"), "name": layer.get("name")} for layer in layers],
        "results": results,
        "failures": failures,
    }


def display_broad_market_results(results: List[Dict]) -> List[Dict]:
    max_rows = int(os.getenv("BROAD_MARKET_DISPLAY_ROWS", "8"))
    return results[:max_rows]


def default_ifind_market_structure() -> Dict:
    return {
        "enabled": True,
        "source": "iFind weekly snapshot",
        "as_of": "2026-05-22",
        "style_summary": "Small/mid-cap growth is leading large-cap indices, but breadth is weak and valuations are elevated.",
        "breadth": {
            "advancers": 1694,
            "decliners": 3512,
            "median_pct_change": -2.17,
        },
        "indices": {
            "上证指数": {"weekly_pct": -0.54, "monthly_pct": 0.02, "ytd_pct": 3.63},
            "深证成指": {"weekly_pct": 0.23, "monthly_pct": 3.24, "ytd_pct": 15.32},
            "沪深300": {"weekly_pct": -0.30, "monthly_pct": 0.79, "ytd_pct": 4.65},
            "中证500": {"weekly_pct": 0.48, "monthly_pct": 2.72, "ytd_pct": 14.89},
            "中证1000": {"weekly_pct": 0.12, "monthly_pct": 3.71, "ytd_pct": 14.45},
            "中证2000": {"weekly_pct": 0.02, "monthly_pct": 4.33, "ytd_pct": 14.40},
            "创业板指": {"weekly_pct": 0.24, "monthly_pct": 7.11, "ytd_pct": 22.96},
        },
        "strong_industries": [
            {"name": "电子", "weekly_pct": 6.56, "ytd_pct": 46.35},
            {"name": "建筑材料", "weekly_pct": 2.61, "ytd_pct": 24.41},
            {"name": "机械设备", "weekly_pct": 1.92, "ytd_pct": 21.00},
            {"name": "综合", "weekly_pct": 0.36, "ytd_pct": 25.58},
            {"name": "电力设备", "weekly_pct": 0.08, "ytd_pct": 16.59},
        ],
        "weak_industries": [
            {"name": "农林牧渔", "weekly_pct": -6.31, "ytd_pct": -13.97},
            {"name": "石油石化", "weekly_pct": -4.70, "ytd_pct": 6.83},
            {"name": "美容护理", "weekly_pct": -4.23, "ytd_pct": -14.82},
            {"name": "钢铁", "weekly_pct": -4.08, "ytd_pct": -7.72},
            {"name": "传媒", "weekly_pct": -4.03, "ytd_pct": -6.76},
            {"name": "房地产", "weekly_pct": -3.69, "ytd_pct": -4.34},
            {"name": "商贸零售", "weekly_pct": -3.23, "ytd_pct": -17.71},
            {"name": "医药生物", "weekly_pct": -2.43, "ytd_pct": -4.70},
        ],
        "industry_aliases": {
            "电子": ["电子", "半导体", "芯片", "集成电路", "消费电子", "光学光电子", "元件", "PCB"],
            "建筑材料": ["建筑材料", "水泥", "玻璃玻纤", "装修建材"],
            "机械设备": ["机械设备", "机器人", "自动化设备", "工程机械", "通用设备", "专用设备"],
            "电力设备": ["电力设备", "电池", "光伏设备", "风电设备", "电网设备", "新能源"],
            "农林牧渔": ["农林牧渔", "养殖业", "种植业", "饲料", "渔业"],
            "石油石化": ["石油石化", "油气开采", "炼化", "石油加工"],
            "美容护理": ["美容护理", "化妆品", "医美"],
            "钢铁": ["钢铁", "普钢", "特钢"],
            "传媒": ["传媒", "游戏", "广告营销", "影视院线"],
            "房地产": ["房地产", "房地产开发", "物业服务"],
            "商贸零售": ["商贸零售", "零售", "贸易"],
            "医药生物": ["医药生物", "化学制药", "中药", "医疗器械", "医疗服务", "生物制品"],
        },
        "valuation_pe_percentile": {
            "上证50": 56.16,
            "沪深300": 69.55,
            "中证500": 69.48,
            "中证1000": 74.59,
            "中证2000": 83.89,
        },
        "basis": {
            "IC00.CFE": {"weekly_basis_change_pct": 1.13, "monthly_basis_change_pct": 0.90, "annualized_carry_pct": -11.16},
            "IM00.CFE": {"weekly_basis_change_pct": 1.15, "monthly_basis_change_pct": 0.76, "annualized_carry_pct": -10.98},
            "IF00.CFE": {"weekly_basis_change_pct": 1.02, "monthly_basis_change_pct": 0.80, "annualized_carry_pct": -10.95},
        },
    }


def load_market_structure() -> Dict:
    path = Path(os.getenv("IFIND_MARKET_STRUCTURE_FILE", "data/ifind_market_structure.json"))
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("enabled", True)
                payload.setdefault("source", str(path))
                return payload
        except Exception as exc:
            logger.warning("Invalid iFind market structure file %s: %s", path, exc)
    if env_enabled("IFIND_MARKET_STRUCTURE_ENABLED", "true"):
        return default_ifind_market_structure()
    return {"enabled": False, "source": "disabled", "regime": "UNKNOWN", "notes": []}


def market_structure_policy(structure: Optional[Dict]) -> Dict:
    structure = structure or {}
    if not structure.get("enabled"):
        return {
            "enabled": False,
            "regime": "UNKNOWN",
            "risk_level": "NEUTRAL",
            "preferred_industries": [],
            "avoid_industries": [],
            "chase_limit_pct": float(os.getenv("BROAD_MARKET_ACTION_MAX_PCT", "5.2")),
            "notes": ["iFind market structure layer disabled."],
        }

    indices = structure.get("indices") or {}
    hs300 = safe_float((indices.get("沪深300") or {}).get("weekly_pct")) or 0
    small_caps = [
        safe_float((indices.get(name) or {}).get("weekly_pct")) or 0
        for name in ("中证500", "中证1000", "中证2000", "创业板指")
    ]
    small_advantage = (max(small_caps) - hs300) >= 0.5 if small_caps else False
    breadth = structure.get("breadth") or {}
    advancers = int(breadth.get("advancers") or 0)
    decliners = int(breadth.get("decliners") or 0)
    weak_breadth = bool(decliners and advancers and decliners > advancers)
    pe = structure.get("valuation_pe_percentile") or {}
    elevated_growth_pe = max(
        safe_float(pe.get("中证1000")) or 0,
        safe_float(pe.get("中证2000")) or 0,
    ) >= 70

    preferred = [item.get("name") for item in structure.get("strong_industries", []) if item.get("name")]
    avoid = [item.get("name") for item in structure.get("weak_industries", []) if item.get("name")]
    regime = "STRUCTURAL_GROWTH_OFFENSE" if small_advantage else "BALANCED_OR_DEFENSIVE"
    chase_limit = float(os.getenv("IFIND_GROWTH_CHASE_LIMIT_PCT", "4.2")) if elevated_growth_pe else float(os.getenv("BROAD_MARKET_ACTION_MAX_PCT", "5.2"))
    risk_level = "SELECTIVE" if (weak_breadth or elevated_growth_pe) else "OPEN"

    notes = []
    if small_advantage:
        notes.append("中小盘/成长风格强于沪深300，短线优先看成长主线。")
    if weak_breadth:
        notes.append(f"涨跌家数偏弱：上涨{advancers}、下跌{decliners}，不是普涨行情。")
    if elevated_growth_pe:
        notes.append("中证1000/2000估值分位偏高，追高阈值下调。")
    if preferred:
        notes.append("强势行业优先：" + " / ".join(preferred[:5]))
    if avoid:
        notes.append("弱势行业降级：" + " / ".join(avoid[:6]))

    return {
        "enabled": True,
        "source": structure.get("source", "iFind"),
        "as_of": structure.get("as_of", ""),
        "regime": regime,
        "risk_level": risk_level,
        "preferred_industries": preferred,
        "avoid_industries": avoid,
        "chase_limit_pct": chase_limit,
        "small_cap_advantage": small_advantage,
        "weak_breadth": weak_breadth,
        "elevated_growth_pe": elevated_growth_pe,
        "notes": notes,
    }


def market_structure_industry_matches(industry: str, names: List[str], structure: Optional[Dict]) -> List[str]:
    aliases = (structure or {}).get("industry_aliases") or {}
    industry_text = str(industry or "")
    matches = []
    for name in names:
        if not name:
            continue
        terms = aliases.get(name) or [name]
        if any(str(term) and str(term) in industry_text for term in terms):
            matches.append(name)
    return matches


def market_structure_gate(item: Dict, structure: Optional[Dict]) -> Dict:
    policy = market_structure_policy(structure)
    industry = str(item.get("industry") or "")
    if not policy.get("enabled"):
        return {"allowed": True, "tone": "neutral", "reason": "iFind结构层未启用", "policy": policy}

    preferred = market_structure_industry_matches(industry, policy.get("preferred_industries", []), structure)
    avoided = market_structure_industry_matches(industry, policy.get("avoid_industries", []), structure)
    if avoided:
        return {
            "allowed": False,
            "tone": "avoid",
            "reason": f"iFind结构层显示{avoided[0]}为弱势行业，短线降级观察。",
            "policy": policy,
        }
    if policy.get("regime") == "STRUCTURAL_GROWTH_OFFENSE" and preferred:
        return {
            "allowed": True,
            "tone": "preferred",
            "reason": f"iFind结构层偏向中小盘成长，且命中强势行业{preferred[0]}。",
            "policy": policy,
        }
    if policy.get("regime") == "STRUCTURAL_GROWTH_OFFENSE":
        return {
            "allowed": False,
            "tone": "neutral_blocked",
            "reason": "iFind结构层显示成长主线占优，但该标的未命中强势行业，短线降级观察。",
            "policy": policy,
        }
    return {"allowed": True, "tone": "neutral", "reason": "iFind结构层未限制该行业。", "policy": policy}


def broad_market_tiers(results: List[Dict], portfolio: Optional[Dict] = None, market_structure: Optional[Dict] = None) -> Dict[str, List[Dict]]:
    strength_rows = int(os.getenv("BROAD_MARKET_STRENGTH_ROWS", "50"))
    watch_rows = int(os.getenv("BROAD_MARKET_WATCH_ROWS", "10"))
    pilot = short_term_pilot_policy(portfolio or {})
    action_rows = int(pilot.get("max_stocks") or os.getenv("BROAD_MARKET_ACTION_ROWS", "3"))
    action_min_amount = float(os.getenv("BROAD_MARKET_ACTION_MIN_AMOUNT", "500000000"))
    action_min_pct = float(os.getenv("BROAD_MARKET_ACTION_MIN_PCT", "1.8"))
    action_max_pct = float(os.getenv("BROAD_MARKET_ACTION_MAX_PCT", "5.2"))
    action_min_volume_ratio = float(os.getenv("BROAD_MARKET_ACTION_MIN_VOLUME_RATIO", "1.2"))
    action_max_volume_ratio = float(os.getenv("BROAD_MARKET_ACTION_MAX_VOLUME_RATIO", "4.5"))
    action_min_turnover = float(os.getenv("BROAD_MARKET_ACTION_MIN_TURNOVER", "0.8"))
    action_max_turnover = float(os.getenv("BROAD_MARKET_ACTION_MAX_TURNOVER", "12"))
    action_min_score = float(os.getenv("BROAD_MARKET_ACTION_MIN_SCORE", "8.0"))
    structure_policy = market_structure_policy(market_structure)
    if structure_policy.get("enabled"):
        action_max_pct = min(action_max_pct, float(structure_policy.get("chase_limit_pct") or action_max_pct))

    actionable = []
    for item in results:
        pct = item.get("pct_change")
        amount = item.get("amount")
        volume_ratio = item.get("volume_ratio")
        turnover = item.get("turnover")
        if item.get("data_quality") != "full":
            continue
        if pct is None or amount is None or volume_ratio is None or turnover is None:
            continue
        if amount < action_min_amount:
            continue
        if pct < action_min_pct or pct > action_max_pct:
            continue
        if volume_ratio < action_min_volume_ratio or volume_ratio > action_max_volume_ratio:
            continue
        if turnover < action_min_turnover or turnover > action_max_turnover:
            continue
        if float(item.get("score") or 0) < action_min_score:
            continue
        structure_gate = market_structure_gate(item, market_structure)
        if not structure_gate.get("allowed"):
            continue
        action_item = dict(item)
        action_item["market_structure_gate"] = structure_gate
        board = item.get("board") or board_label(str(item.get("code", "")))
        if board != "沪深主板":
            action_item["action"] = f"{board}观察，先确认权限和20cm波动风险"
            reason_prefix = f"已扫描到{board}标的，但当前只作为全市场观察，不直接纳入默认下单池"
        elif item.get("theme_layers"):
            action_item["action"] = "观察候选，非动作卡；需单独通过动作卡才可买"
            reason_prefix = "通过主线短线过滤，进入观察候选；不等于实盘买入，必须再通过主线分、执行分、风控和确认窗口"
        else:
            action_item["action"] = "全市场异动备选，需降级观察"
            reason_prefix = "通过全市场量价过滤，但未命中当前AI/数字基建主线；只能作为备选，不优先下单"
        action_item["reasons"] = [
            structure_gate.get("reason", ""),
            reason_prefix,
            *item.get("reasons", []),
        ]
        actionable.append(action_item)

    theme_actionable = [item for item in actionable if item.get("theme_layers")]
    fallback_actionable = [item for item in actionable if not item.get("theme_layers")]
    actionable = (theme_actionable + fallback_actionable)[:action_rows]

    return {
        "strength": results[:strength_rows],
        "watch": results[:watch_rows],
        "actionable": actionable,
    }


def short_term_pilot_policy(portfolio: Dict) -> Dict:
    return (portfolio.get("capital_plan") or {}).get("short_term_pilot") or {}


def broad_market_coverage_gate(report: Dict) -> Dict:
    broad_scan = report.get("broad_market_scan") or {}
    if not broad_scan.get("enabled"):
        return {
            "blocked": True,
            "level": "DATA_DISABLED",
            "reason": "全市场扫描未启用，短线动作卡降级观察。",
        }

    try:
        target = int(broad_scan.get("min_rows_target") or os.getenv("BROAD_MARKET_MIN_ROWS", "5000"))
        scanned = int(broad_scan.get("scanned_count") or 0)
    except (TypeError, ValueError):
        target = int(os.getenv("BROAD_MARKET_MIN_ROWS", "5000"))
        scanned = 0

    if scanned < target:
        return {
            "blocked": True,
            "level": "DATA_INCOMPLETE",
            "reason": f"全市场扫描只读取{scanned}只，低于{target}只目标；今日短线动作卡降级观察。",
            "scanned_count": scanned,
            "min_rows_target": target,
            "missing_estimate": max(target - scanned, 0),
        }

    return {
        "blocked": False,
        "level": "OK",
        "reason": f"全市场扫描读取{scanned}只，达到{target}只覆盖目标。",
        "scanned_count": scanned,
        "min_rows_target": target,
        "missing_estimate": 0,
    }


def short_term_policy_sentence(portfolio: Dict) -> str:
    pilot = short_term_pilot_policy(portfolio)
    if not pilot:
        return "短线试运行未启用；只做观察，不开新仓。"
    return (
        f"可操作池最多{pilot.get('max_stocks', 3)}只；"
        f"B级单只默认{yuan(pilot.get('capital_per_stock'))}；"
        f"A级强确认最多{yuan(pilot.get('strong_signal_capital_per_stock'))}；"
        f"短线总额不超过{yuan(pilot.get('max_total_capital'))}；"
        f"日目标{yuan(pilot.get('daily_profit_target'))}只是测算目标，不用于倒逼交易。"
    )


def short_term_pilot_title(pilot: Dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(BEIJING_TZ)
    stage = pilot.get("stage") or "每日短线动作卡"
    return f"{now.strftime('%Y-%m-%d')} {stage}"


def daily_risk_gate(portfolio: Dict, pilot: Dict) -> Dict:
    daily_profit = float(portfolio.get("daily_profit") or 0)
    soft_stop = float(pilot.get("daily_loss_soft_stop") or -1200)
    hard_stop = float(pilot.get("daily_loss_hard_stop") or -2000)
    if daily_profit <= hard_stop:
        return {
            "blocked": True,
            "level": "HARD_STOP",
            "reason": f"当日盈亏 {daily_profit:.0f} 元已触发硬熔断 {hard_stop:.0f} 元，停止新开仓",
        }
    if daily_profit <= soft_stop:
        return {
            "blocked": False,
            "level": "SOFT_STOP",
            "reason": f"当日盈亏 {daily_profit:.0f} 元接近软熔断 {soft_stop:.0f} 元，只允许减仓或极小试错",
        }
    return {"blocked": False, "level": "OPEN", "reason": "当日风险闸门未触发"}


def tactical_cash_policy(portfolio: Dict) -> Dict:
    plan = portfolio.get("capital_plan") or {}
    policy = plan.get("tactical_callable_cash") or {}
    deployment = plan.get("liquidity_deployment_plan") or {}
    amount = safe_float(policy.get("amount"))
    if amount is None:
        amount = safe_float(portfolio.get("tactical_callable_cash"))
    batch_size = safe_float(policy.get("batch_size"))
    if batch_size is None:
        batch_size = safe_float(deployment.get("tactical_cash_batch_size"))
    return {
        "amount": amount or 0,
        "on_exchange_asset_snapshot": safe_float(policy.get("on_exchange_asset_snapshot")) or safe_float(deployment.get("on_exchange_asset_snapshot")) or safe_float(portfolio.get("on_exchange_asset_snapshot")) or 0,
        "total_callable_capital": safe_float(policy.get("total_callable_capital")) or safe_float(deployment.get("total_callable_capital")) or safe_float(portfolio.get("total_callable_capital")) or 0,
        "batch_size": batch_size or 50_000,
        "default_monday_open_transfer": safe_float(policy.get("default_monday_open_transfer")) or 0,
        "rule": policy.get("rule") or deployment.get("external_cash_transfer_rule") or "",
        "forbidden_uses": policy.get("forbidden_uses") or [],
        "batch_triggers": policy.get("batch_triggers") or [],
    }


def tactical_cash_decision(report: Dict, stock_cards: Optional[List[Dict]] = None) -> Dict:
    portfolio = report.get("portfolio") or {}
    pilot = short_term_pilot_policy(portfolio)
    policy = tactical_cash_policy(portfolio)
    risk_gate = daily_risk_gate(portfolio, pilot) if pilot else {
        "blocked": True,
        "level": "DISABLED",
        "reason": "短线试运行未启用",
    }
    coverage_gate = broad_market_coverage_gate(report)
    stock_cards = stock_cards if stock_cards is not None else short_term_action_cards(report)
    actionable = [
        item
        for item in stock_cards
        if safe_float(item.get("capital")) and int(item.get("shares") or 0) > 0
    ]
    watchable = [
        item
        for item in stock_cards
        if int(item.get("layer_resonance_score") or 0) >= 2
        and int(item.get("execution_quality_score") or 0) >= 7
    ]

    amount = float(policy.get("amount") or 0)
    batch = float(policy.get("batch_size") or 50_000)
    daily_profit = float(portfolio.get("daily_profit") or 0)

    decision = {
        "status": "HOLD",
        "label": "不转入",
        "allowed_transfer_amount": 0,
        "max_cumulative_transfer": 0,
        "tactical_callable_cash": amount,
        "on_exchange_asset_snapshot": float(policy.get("on_exchange_asset_snapshot") or 0),
        "total_callable_capital": float(policy.get("total_callable_capital") or 0),
        "batch_size": batch,
        "actionable_count": len(actionable),
        "watchable_count": len(watchable),
        "daily_profit": daily_profit,
        "risk_gate": risk_gate,
        "data_coverage_gate": coverage_gate,
        "reason": "默认不转入；先让工作台证明机会。",
        "next_check": "09:40",
        "forbidden_uses": policy.get("forbidden_uses") or [],
    }

    if amount <= 0:
        decision.update({
            "status": "DISABLED",
            "label": "未配置战术现金",
            "reason": "portfolio.json 未配置 tactical_callable_cash。",
        })
        return decision
    if coverage_gate.get("blocked"):
        decision["reason"] = coverage_gate.get("reason") or "全市场覆盖不足，战术现金不进场。"
        return decision
    if risk_gate.get("blocked") or risk_gate.get("level") in {"SOFT_STOP", "HARD_STOP"}:
        decision["reason"] = risk_gate.get("reason") or "风险闸门未打开，战术现金不进场。"
        decision["next_check"] = "14:40"
        return decision
    if len(actionable) >= 2:
        allowed = min(batch, amount)
        decision.update({
            "status": "ALLOW_BATCH_1",
            "label": "可转第1批",
            "allowed_transfer_amount": allowed,
            "max_cumulative_transfer": allowed,
            "reason": f"出现 {len(actionable)} 张可执行动作卡，且风控/数据闸门打开；只允许先转 {yuan(allowed)}。",
            "next_check": "10:45",
        })
        return decision
    if len(actionable) == 1:
        allowed = min(batch, amount)
        decision.update({
            "status": "CONDITIONAL_BATCH_1",
            "label": "条件允许5万",
            "allowed_transfer_amount": allowed,
            "max_cumulative_transfer": allowed,
            "reason": f"只有 1 张可执行动作卡；可以准备 {yuan(allowed)}，但买点必须由 09:40/10:45 二次确认。",
            "next_check": "10:45",
        })
        return decision
    if len(watchable) >= 2:
        decision.update({
            "status": "WATCH",
            "label": "观察，不转",
            "reason": f"有 {len(watchable)} 张接近动作卡的候选，但仓位/买点尚未放行；钱先不进。",
            "next_check": "10:45",
        })
        return decision
    return decision


def minimum_lot_size(code: str) -> int:
    if str(code).startswith("688"):
        return 200
    return 100


def short_term_trade_plan(item: Dict, portfolio: Dict) -> Dict:
    pilot = short_term_pilot_policy(portfolio)
    if not pilot or not pilot.get("enabled"):
        return {"tier": "观察", "capital": None, "reason": "短线试运行未启用"}

    risk_gate = daily_risk_gate(portfolio, pilot)
    pct = item.get("pct_change")
    amount = item.get("amount") or 0
    ma20 = item.get("ma20")
    ma60 = item.get("ma60")
    price = item.get("price")
    level = item.get("level")
    lot_size = minimum_lot_size(str(item.get("code") or ""))
    min_lot_cost = (float(price) * lot_size) if price is not None else None

    if risk_gate["blocked"]:
        return {"tier": "禁止新开", "capital": 0, "reason": risk_gate["reason"]}
    if level == "RED":
        return {"tier": "禁止追买", "capital": 0, "reason": "红色信号，优先保护本金"}
    if pct is None or price is None:
        return {"tier": "观察", "capital": 0, "reason": "数据不足，不能放大仓位"}
    if pct >= float(pilot.get("no_chase_pct", 5.2)):
        return {"tier": "等回踩", "capital": 0, "reason": f"涨幅 {pct:.2f}% 已接近追高区，等二次确认"}
    if pct <= float(pilot.get("avoid_weak_pct", -3.5)):
        return {"tier": "观察承接", "capital": 0, "reason": f"跌幅 {pct:.2f}% 较大，先看承接不急买"}

    default_capital = float(pilot.get("capital_per_stock") or 0)
    strong_capital = float(pilot.get("strong_signal_capital_per_stock") or default_capital)
    max_allowed_capital = max(default_capital, strong_capital)
    if min_lot_cost and min_lot_cost > max_allowed_capital:
        return {
            "tier": "观察",
            "capital": 0,
            "reason": f"最小一手约{yuan(min_lot_cost)}，超过当前单票上限{yuan(max_allowed_capital)}，不强行放大仓位",
        }

    trend_ok = bool(price and ma20 and ma60 and price > ma20 > ma60)
    active_ok = amount >= float(pilot.get("min_action_amount", 500_000_000))
    pct_ok = float(pilot.get("action_min_pct", 1.2)) <= pct <= float(pilot.get("action_max_pct", 5.2))

    if trend_ok and active_ok and pct_ok and risk_gate["level"] == "OPEN":
        return {
            "tier": "A级试单",
            "capital": pilot.get("strong_signal_capital_per_stock"),
            "reason": "趋势、成交额和涨幅区间同时达标；仍需9:40/10:45二次确认",
        }
    if active_ok and pct_ok:
        return {
            "tier": "B级试单",
            "capital": pilot.get("capital_per_stock"),
            "reason": "量价进入可观察区，但趋势或风控条件未完全共振，只能默认仓",
        }
    return {"tier": "观察", "capital": 0, "reason": "未达到短线扩容条件"}


def display_stock_results(results: List[Dict]) -> List[Dict]:
    max_rows = int(os.getenv("AI_STOCK_DISPLAY_ROWS", "40"))
    focus_codes = list(focus_stock_codes())
    by_code = {str(item.get("code")): item for item in results}
    selected = []
    selected_codes = set()

    for code in focus_codes:
        item = by_code.get(code)
        if item and code not in selected_codes:
            selected.append(item)
            selected_codes.add(code)

    for item in results:
        code = str(item.get("code"))
        if code not in selected_codes:
            selected.append(item)
            selected_codes.add(code)
        if len(selected) >= max_rows:
            break

    return selected[:max_rows]


def round_lot_shares(capital: Optional[float], price: Optional[float], lot_size: int) -> int:
    if not capital or not price or price <= 0:
        return 0
    lots = int(float(capital) // (float(price) * lot_size))
    return max(lots * lot_size, 0)


def latest_execution_events() -> List[Dict]:
    path = Path(EXECUTION_EVENTS_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def recent_paper_trade_rows() -> List[Dict[str, str]]:
    return load_csv_rows(PAPER_TRADE_JOURNAL_PATH)


def failed_trial_count_today(report: Dict) -> int:
    generated_at = str(report.get("generated_at") or "")
    trade_date = generated_at.split(" ", 1)[0] if generated_at else ""
    if not trade_date:
        return 0

    failed = 0
    seen_codes = set()
    for row in recent_paper_trade_rows():
        if str(row.get("date") or "") != trade_date:
            continue
        code = str(row.get("code") or "")
        outcome = str(row.get("outcome") or "").strip()
        pnl_pct = safe_float(row.get("pnl_pct"))
        review = str(row.get("review") or "")
        text = f"{outcome} {review}"
        is_fail = False
        if outcome in {"已卖出", "失败", "止损"} and pnl_pct is not None and pnl_pct < 0:
            is_fail = True
        elif "止损" in text or "失败" in text:
            is_fail = True
        if is_fail and code not in seen_codes:
            failed += 1
            seen_codes.add(code)
    return failed


def stop_new_entries_gate(report: Dict, pilot: Dict) -> Dict:
    failure_limit = int(pilot.get("max_failed_trials_per_day") or 2)
    failed_count = failed_trial_count_today(report)
    blocked = failed_count >= failure_limit
    return {
        "blocked": blocked,
        "failure_limit": failure_limit,
        "failed_count_today": failed_count,
        "reason": (
            f"今日已出现 {failed_count} 次试错失败，达到停手线 {failure_limit} 次，停止新开仓。"
            if blocked
            else f"今日试错失败 {failed_count}/{failure_limit} 次，仍可等待下一确认窗口。"
        ),
    }


def turtle_position_sizing(item: Dict, portfolio: Dict, stop_loss: Optional[float], base_capital: float) -> Dict:
    code = str(item.get("code") or "")
    price = safe_float(item.get("price"))
    total_capital = safe_float(portfolio.get("total_capital")) or 0
    pilot = short_term_pilot_policy(portfolio)
    lot_size = minimum_lot_size(code)
    risk_pct = float(pilot.get("single_trade_risk_pct") or 0.005)
    risk_budget = total_capital * risk_pct if total_capital > 0 else 0
    risk_per_share = (price - stop_loss) if price is not None and stop_loss is not None else None
    stop_sized_shares = 0
    stop_sized_capital = 0.0

    if risk_budget > 0 and risk_per_share is not None and risk_per_share > 0 and price:
        raw_shares = int(risk_budget // risk_per_share)
        stop_sized_shares = max((raw_shares // lot_size) * lot_size, 0)
        stop_sized_capital = float(stop_sized_shares) * float(price)

    chosen_capital = min(base_capital, stop_sized_capital) if stop_sized_capital > 0 else 0.0
    chosen_shares = round_lot_shares(chosen_capital, price, lot_size)
    if stop_sized_shares > 0:
        chosen_shares = min(chosen_shares, stop_sized_shares)
        chosen_capital = float(chosen_shares) * float(price) if price else 0.0

    max_loss_if_stopped = (
        float(chosen_shares) * float(risk_per_share)
        if chosen_shares > 0 and risk_per_share is not None and risk_per_share > 0
        else 0.0
    )
    blocked_reason = ""
    if price is None or stop_loss is None:
        blocked_reason = "缺少价格或止损线，无法按止损反推仓位"
    elif risk_per_share is None or risk_per_share <= 0:
        blocked_reason = "止损线无效，无法计算单股风险"
    elif stop_sized_shares <= 0:
        blocked_reason = f"风险预算 {yuan(risk_budget)} 不足以覆盖最小一手 {lot_size} 股"

    return {
        "risk_per_trade_pct": risk_pct,
        "risk_per_trade_amount": risk_budget,
        "risk_per_share": risk_per_share,
        "sized_by_stop_shares": stop_sized_shares,
        "sized_by_stop_capital": stop_sized_capital,
        "chosen_shares": chosen_shares,
        "chosen_capital": chosen_capital,
        "max_loss_if_stopped": max_loss_if_stopped,
        "lot_size": lot_size,
        "blocked_reason": blocked_reason,
    }


def add_on_permission(item: Dict, portfolio: Dict) -> Dict:
    code = str(item.get("code") or "")
    price = safe_float(item.get("price"))
    pos = position_map(portfolio).get(code)
    if not pos or safe_float(pos.get("shares")) <= 0:
        return {"held": False, "allowed": False, "reason": "当前无持仓，这不是加仓场景。"}

    cost = safe_float(pos.get("cost"))
    if price is None or cost is None or cost <= 0:
        return {"held": True, "allowed": False, "reason": "已有持仓，但成本或现价不完整，默认不加仓。"}
    if price <= cost:
        return {"held": True, "allowed": False, "reason": f"现价 {fmt(price)} 未站上成本 {fmt(cost)}，亏损仓不加仓。"}
    return {"held": True, "allowed": True, "reason": f"现价 {fmt(price)} 高于成本 {fmt(cost)}，只允许盈利仓讨论加仓。"}


def layer_resonance_score(item: Dict, all_results: List[Dict]) -> int:
    layers = item.get("theme_layers") or []
    if not layers:
        return 0
    layer_set = set(layers)
    peers = [
        row
        for row in all_results
        if layer_set.intersection(set(row.get("theme_layers") or []))
        and (row.get("pct_change") or 0) >= 1.2
        and (row.get("amount") or 0) >= 300_000_000
    ]
    if len(peers) >= 4 and (item.get("amount") or 0) >= 1_000_000_000:
        return 3
    if len(peers) >= 2:
        return 2
    return 1


def execution_quality_score(item: Dict, pilot: Dict) -> int:
    score = 0
    pct = item.get("pct_change")
    amount = item.get("amount") or 0
    volume_ratio = item.get("volume_ratio")
    turnover = item.get("turnover")
    intraday_pct = item.get("intraday_pct")
    no_chase_pct = float(pilot.get("no_chase_pct") or 5.2)

    if amount >= float(pilot.get("min_action_amount") or 500_000_000):
        score += 2
    if volume_ratio is not None and 1.2 <= volume_ratio <= 4.5:
        score += 2
    if turnover is not None and 0.8 <= turnover <= 12:
        score += 2
    if pct is not None and 1.2 <= pct < no_chase_pct:
        score += 2
    if intraday_pct is not None and intraday_pct >= -0.5:
        score += 2
    return min(score, 10)


def position_permission_for_item(item: Dict, portfolio: Dict, capital: float, shares: Optional[int] = None) -> Dict:
    code = str(item.get("code") or "")
    price = safe_float(item.get("price"))
    lot_size = minimum_lot_size(code)
    shares = int(shares if shares is not None else round_lot_shares(capital, price, lot_size))
    pilot = short_term_pilot_policy(portfolio)
    max_total = float(pilot.get("max_total_capital") or 0)
    max_new_buy = float((portfolio.get("capital_plan") or {}).get("liquidity_deployment_plan", {}).get("stage_1_max_new_buy_per_day") or 0)
    board = item.get("board") or board_label(code)
    blocked_reason = ""

    if not price:
        blocked_reason = "缺少价格，不能下单"
    elif board != "沪深主板":
        blocked_reason = f"{board}权限和20cm波动风险更高，默认不纳入实盘动作"
    elif capital <= 0 or shares <= 0:
        blocked_reason = "仓位规则不允许开仓"
    elif max_new_buy and capital > max_new_buy:
        blocked_reason = f"超过单日新开仓上限 {yuan(max_new_buy)}"

    return {
        "allowed": blocked_reason == "",
        "max_capital": capital,
        "lot_size": lot_size,
        "estimated_shares": shares,
        "blocked_reason": blocked_reason,
        "bucket_after_trade": capital if blocked_reason == "" else 0,
        "bucket_limit": max_total,
    }


def decision_card_for_item(
    item: Dict,
    can_do: bool,
    capital: float,
    shares: int,
    entry_low,
    entry_high,
    take_profit_1,
    take_profit_2,
    stop_loss,
    turtle_sizing: Optional[Dict] = None,
    add_on_gate: Optional[Dict] = None,
    stop_new_entries_gate_payload: Optional[Dict] = None,
) -> Dict:
    turtle_sizing = turtle_sizing or {}
    add_on_gate = add_on_gate or {}
    stop_new_entries_gate_payload = stop_new_entries_gate_payload or {}
    if can_do:
        risk_budget = turtle_sizing.get("risk_per_trade_amount")
        max_loss = turtle_sizing.get("max_loss_if_stopped")
        return {
            "decision": "做",
            "grade": "B",
            "window": "9:40/10:45/14:40",
            "entry_range": [entry_low, entry_high],
            "max_capital": capital,
            "estimated_shares": shares,
            "take_profit": [take_profit_1, take_profit_2],
            "stop_loss": stop_loss,
            "risk_per_trade_amount": risk_budget,
            "max_loss_if_stopped": max_loss,
            "add_on_allowed": bool(add_on_gate.get("allowed")),
            "stop_new_entries_today": bool(stop_new_entries_gate_payload.get("blocked")),
            "plain_text": (
                f"B级试单，最多{yuan(capital)}，约{shares}股；"
                f"若打止损，理论最大试错约{yuan(max_loss)} / 单笔风险预算{yuan(risk_budget)}；"
                "只在确认窗口执行，不追高。"
            ),
        }
    return {
        "decision": "不做",
        "grade": "NO_TRADE",
        "window": "观察",
        "entry_range": [],
        "max_capital": 0,
        "estimated_shares": 0,
        "take_profit": [],
        "stop_loss": None,
        "risk_per_trade_amount": turtle_sizing.get("risk_per_trade_amount"),
        "max_loss_if_stopped": turtle_sizing.get("max_loss_if_stopped"),
        "add_on_allowed": bool(add_on_gate.get("allowed")),
        "stop_new_entries_today": bool(stop_new_entries_gate_payload.get("blocked")),
        "plain_text": "今天不进入实盘动作；只观察是否进入下一次动作池。",
    }


def xingyao_status_text(option_radar: Dict) -> str:
    if option_radar.get("xingyao_enabled") and option_radar.get("xingyao_contract_count", 0):
        return f"星耀已接入：读取到 {option_radar.get('xingyao_contract_count', 0)} 条期权基础合约。"
    error = option_radar.get("xingyao_error") or "未启用"
    if error == "disabled":
        return "星耀未启用：本次邮件仍用模拟权利金，不是真实期权链。"
    if error == "missing credentials":
        return "星耀未启用：缺少账号或密码环境变量。"
    return f"星耀未接入成功：{error}；本次仍用模拟权利金。"


def short_term_action_cards(report: Dict) -> List[Dict]:
    portfolio = report.get("portfolio", {})
    pilot = short_term_pilot_policy(portfolio)
    broad_scan = report.get("broad_market_scan", {})
    broad_results = broad_scan.get("results", [])
    market_structure = report.get("market_structure", {})
    structure_policy = report.get("market_structure_policy") or market_structure_policy(market_structure)
    tiers = broad_market_tiers(broad_results, portfolio, market_structure)
    default_capital = float(pilot.get("capital_per_stock") or 0)
    target_profit_pct = float(pilot.get("target_profit_pct") or 0.03)
    stop_loss_pct = float(pilot.get("stop_loss_pct") or 0.03)
    no_chase_pct = min(
        float(pilot.get("no_chase_pct") or 5.2),
        float(structure_policy.get("chase_limit_pct") or 5.2),
    )
    risk_gate = daily_risk_gate(portfolio, pilot) if pilot else {"blocked": True, "level": "DISABLED", "reason": "短线试运行未启用"}
    stop_gate = stop_new_entries_gate(report, pilot) if pilot else {"blocked": False, "failed_count_today": 0, "failure_limit": 2, "reason": "未启用"}
    coverage_gate = broad_market_coverage_gate(report)
    cards = []

    for item in tiers.get("actionable", []):
        code = str(item.get("code") or "")
        price = safe_float(item.get("price"))
        pct = safe_float(item.get("pct_change"))
        lot_size = minimum_lot_size(code)
        board = item.get("board") or board_label(code)
        is_default_board = board == "沪深主板"
        is_theme = bool(item.get("theme_layers"))
        structure_gate = item.get("market_structure_gate") or market_structure_gate(item, market_structure)
        layer_score = layer_resonance_score(item, broad_results)
        execution_score = execution_quality_score(item, pilot)
        base_can_do = bool(
            is_default_board
            and is_theme
            and structure_gate.get("allowed", True)
            and price
            and pct is not None
            and pct < no_chase_pct
            and layer_score >= 2
            and execution_score >= 7
            and not risk_gate.get("blocked")
            and not stop_gate.get("blocked")
            and not coverage_gate.get("blocked")
        )
        initial_capital = default_capital if base_can_do else 0
        entry_low = price * 0.995 if price else None
        entry_high = price * 1.005 if price else None
        take_profit_1 = price * (1 + target_profit_pct) if price else None
        take_profit_2 = price * (1 + min(target_profit_pct + 0.02, 0.05)) if price else None
        stop_loss = price * (1 - stop_loss_pct) if price else None
        turtle_sizing = turtle_position_sizing(item, portfolio, stop_loss, initial_capital)
        capital = float(turtle_sizing.get("chosen_capital") or 0) if base_can_do else 0
        suggested_shares = int(turtle_sizing.get("chosen_shares") or 0) if base_can_do else 0
        position_permission = position_permission_for_item(item, portfolio, capital, suggested_shares)
        shares = int(position_permission.get("estimated_shares") or 0)
        add_on_gate = add_on_permission(item, portfolio)
        holding_add_blocked = bool(add_on_gate.get("held")) and not bool(add_on_gate.get("allowed"))
        can_do = base_can_do and bool(position_permission.get("allowed")) and shares > 0 and not holding_add_blocked
        if not can_do:
            capital = 0
            shares = 0
        decision_card = decision_card_for_item(
            item,
            can_do,
            capital,
            shares,
            entry_low,
            entry_high,
            take_profit_1,
            take_profit_2,
            stop_loss,
            turtle_sizing,
            add_on_gate,
            stop_gate,
        )
        if can_do:
            decision = "做"
            action = decision_card["plain_text"]
        else:
            decision = "不做"
            if coverage_gate.get("blocked"):
                action = coverage_gate.get("reason", "数据覆盖不足，今天只观察。")
            elif board != "沪深主板":
                action = f"{board}波动和权限风险更高，今天只观察。"
            elif not is_theme:
                action = "未命中当前主线，今天只观察。"
            elif layer_score < 2:
                action = "主线共振不足，今天只观察。"
            elif execution_score < 7:
                action = "执行质量不够，今天只观察。"
            elif risk_gate.get("blocked"):
                action = risk_gate.get("reason", "风控闸门关闭，今天不做。")
            elif stop_gate.get("blocked"):
                action = stop_gate.get("reason", "今日试错次数已达上限，停止新开仓。")
            elif holding_add_blocked:
                action = add_on_gate.get("reason", "已有持仓但未通过加仓条件，不新增风险。")
            elif turtle_sizing.get("blocked_reason"):
                action = turtle_sizing.get("blocked_reason")
            else:
                action = "涨幅接近追高区，等回踩，不主动开仓。"
        cards.append(
            {
                "decision": decision,
                "code": code,
                "name": item.get("name"),
                "price": price,
                "pct_change": pct,
                "capital": capital,
                "shares": shares,
                "entry_low": entry_low,
                "entry_high": entry_high,
                "take_profit_1": take_profit_1,
                "take_profit_2": take_profit_2,
                "stop_loss": stop_loss,
                "action": action,
                "reason": "；".join(item.get("reasons", [])[:3]),
                "layer_resonance_score": layer_score,
                "execution_quality_score": execution_score,
                "market_structure_gate": structure_gate,
                "position_permission": position_permission,
                "decision_card": decision_card,
                "risk_gate": risk_gate,
                "stop_new_entries_gate": stop_gate,
                "data_coverage_gate": coverage_gate,
                "risk_per_trade_pct": turtle_sizing.get("risk_per_trade_pct"),
                "risk_per_trade_amount": turtle_sizing.get("risk_per_trade_amount"),
                "risk_per_share": turtle_sizing.get("risk_per_share"),
                "sized_by_stop_shares": turtle_sizing.get("sized_by_stop_shares"),
                "sized_by_stop_capital": turtle_sizing.get("sized_by_stop_capital"),
                "max_loss_if_stopped": turtle_sizing.get("max_loss_if_stopped"),
                "add_on_allowed": add_on_gate.get("allowed"),
                "add_on_reason": add_on_gate.get("reason"),
            }
        )

    return cards


def option_beginner_cards(option_radar: Dict) -> List[Dict]:
    cards = []
    for item in option_radar.get("results", []):
        suitability = str(item.get("suitability") or "")
        can_sim = "可模拟" in suitability
        max_loss = safe_float(item.get("max_loss"))
        premium = safe_float(item.get("premium"))
        if can_sim and max_loss is not None and 100 <= max_loss <= 1500:
            decision = "只仿真"
            action = f"仿真买入1张{item.get('direction')}，最大亏损约{yuan(max_loss)}；当天不做实盘。"
        else:
            decision = "不做"
            action = "方向或赔率不清晰；小白阶段不要为了日目标硬做。"
        cards.append(
            {
                "decision": decision,
                "code": item.get("code"),
                "name": item.get("name"),
                "direction": item.get("direction"),
                "strike": item.get("strike"),
                "premium": premium,
                "contract_cost": item.get("contract_cost"),
                "break_even": item.get("break_even"),
                "max_loss": max_loss,
                "action": action,
                "suitability": suitability,
            }
        )
    return cards


def action_plan_markdown_lines(report: Dict) -> List[str]:
    portfolio = report.get("portfolio", {})
    pilot = short_term_pilot_policy(portfolio)
    stock_cards = short_term_action_cards(report)
    do_cards = [item for item in stock_cards if item["decision"] == "做"]
    option_radar = report.get("option_sim_radar", {})
    option_cards = option_beginner_cards(option_radar)
    option_do_cards = [item for item in option_cards if item["decision"] == "只仿真"]
    coverage_gate = broad_market_coverage_gate(report)
    cash_decision = tactical_cash_decision(report, stock_cards)

    lines = ["", "## 今日动作卡", ""]
    lines.append(f"- 数据闸门：{coverage_gate.get('reason', '全市场覆盖状态未知。')}")
    lines.extend(
        [
            "",
            "### 战术现金调度",
            "",
            f"- 结论：{cash_decision.get('label')}；本次允许转入 {yuan(cash_decision.get('allowed_transfer_amount'))}；战术现金总额 {yuan(cash_decision.get('tactical_callable_cash'))}。",
            f"- 可调动口径：场内资产 {yuan(cash_decision.get('on_exchange_asset_snapshot'))} + 战术现金 {yuan(cash_decision.get('tactical_callable_cash'))} = 总可调动约 {yuan(cash_decision.get('total_callable_capital'))}。",
            f"- 原因：{cash_decision.get('reason')}",
            f"- 下一检查：{cash_decision.get('next_check')}；可执行动作卡 {cash_decision.get('actionable_count')} 张；接近动作卡 {cash_decision.get('watchable_count')} 张。",
            "- 禁止：战术现金不用于摊平宽基/弱ETF，不用于补救盘中情绪，不用于追高。",
        ]
    )
    if do_cards:
        first = do_cards[0]
        lines.extend(
            [
                f"- 短线结论：今天只做 1 只，优先 {first['code']} {first['name']}；默认不把 {yuan(pilot.get('max_total_capital'))} 打满。",
                f"- 买入纪律：最多 {yuan(first['capital'])}，约 {first['shares']} 股；参考区间 {fmt(first['entry_low'])}-{fmt(first['entry_high'])}，必须等9:40/10:45确认。",
                f"- 卖出纪律：第一档 {fmt(first['take_profit_1'])} 附近先落袋一半；第二档 {fmt(first['take_profit_2'])} 附近看承接处理剩余。",
                f"- 止损纪律：跌破 {fmt(first['stop_loss'])} 且收不回，承认试错失败，不补仓摊低。",
            ]
        )
    else:
        lines.append("- 短线结论：今天没有默认可做标的；空手比硬做更重要。")

    if stock_cards:
        lines.extend(["", "| 标的 | 做/不做 | 主线分 | 执行分 | 买多少 | 买入区 | 止盈 | 止损 | 小白解释 |", "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |"])
        for item in stock_cards[:6]:
            lines.append(
                "| {code} {name} | {decision} | {layer_score} | {execution_score} | {capital} / {shares}股 | {entry_low}-{entry_high} | {tp1}/{tp2} | {stop} | {action} |".format(
                    code=markdown_escape(item.get("code")),
                    name=markdown_escape(item.get("name")),
                    decision=markdown_escape(item.get("decision")),
                    layer_score=item.get("layer_resonance_score", 0),
                    execution_score=item.get("execution_quality_score", 0),
                    capital=yuan(item.get("capital")),
                    shares=item.get("shares", 0),
                    entry_low=fmt(item.get("entry_low")),
                    entry_high=fmt(item.get("entry_high")),
                    tp1=fmt(item.get("take_profit_1")),
                    tp2=fmt(item.get("take_profit_2")),
                    stop=fmt(item.get("stop_loss")),
                    action=markdown_escape(item.get("action")),
                )
            )

    lines.extend(["", "### 期权/期货类小白版", ""])
    lines.append(f"- {xingyao_status_text(option_radar)}")
    lines.append("- 期货模块当前没有接入实盘数据；今天不做期货实盘。")
    if option_do_cards:
        first_option = option_do_cards[0]
        lines.append(
            f"- 期权只做仿真：优先观察 {first_option.get('code')} {first_option.get('direction')}，1张以内，最大亏损约 {yuan(first_option.get('max_loss'))}。"
        )
    else:
        lines.append("- 期权结论：今天没有必须模拟的合约；看不懂就不做。")
    return lines


def build_action_stack(report: Dict) -> Dict:
    portfolio = report.get("portfolio", {})
    pilot = short_term_pilot_policy(portfolio)
    risk_gate = daily_risk_gate(portfolio, pilot) if pilot else {
        "blocked": True,
        "level": "DISABLED",
        "reason": "短线试运行未启用",
    }
    stop_gate = stop_new_entries_gate(report, pilot) if pilot else {
        "blocked": False,
        "failed_count_today": 0,
        "failure_limit": 2,
        "reason": "未启用",
    }
    stock_cards = short_term_action_cards(report)
    option_radar = report.get("option_sim_radar", {})
    option_cards = option_beginner_cards(option_radar)
    cash_decision = tactical_cash_decision(report, stock_cards)
    return {
        "generated_at": report.get("generated_at"),
        "risk_gate": risk_gate,
        "stop_new_entries_gate": stop_gate,
        "tactical_cash_decision": cash_decision,
        "data_coverage_gate": broad_market_coverage_gate(report),
        "short_term_cards": stock_cards,
        "option_cards": option_cards,
        "xingyao_status": xingyao_status_text(option_radar),
        "market_structure_policy": report.get("market_structure_policy", {}),
        "fields": [
            "layer_resonance_score",
            "execution_quality_score",
            "market_structure_gate",
            "position_permission",
            "decision_card",
            "risk_gate",
            "stop_new_entries_gate",
            "risk_per_trade_amount",
            "risk_per_share",
            "sized_by_stop_shares",
            "max_loss_if_stopped",
            "add_on_allowed",
            "add_on_reason",
        ],
    }


def action_plan_html(report: Dict) -> str:
    stock_cards = short_term_action_cards(report)
    option_radar = report.get("option_sim_radar", {})
    option_cards = option_beginner_cards(option_radar)
    do_cards = [item for item in stock_cards if item["decision"] == "做"]
    option_do_cards = [item for item in option_cards if item["decision"] == "只仿真"]
    coverage_gate = broad_market_coverage_gate(report)
    cash_decision = tactical_cash_decision(report, stock_cards)

    if do_cards:
        first = do_cards[0]
        summary = (
            f"今天只做 1 只：{html.escape(str(first.get('code')))} {html.escape(str(first.get('name')))}。"
            f"最多 {yuan(first.get('capital'))}，约 {html.escape(str(first.get('shares')))} 股；"
            f"止盈看 {fmt(first.get('take_profit_1'))}/{fmt(first.get('take_profit_2'))}，"
            f"止损看 {fmt(first.get('stop_loss'))}。"
        )
    else:
        summary = "今天没有默认可做标的；空手比硬做更重要。"

    stock_rows = []
    for item in stock_cards[:6]:
        color = "#1a7f37" if item.get("decision") == "做" else "#d1242f"
        stock_rows.append(
            f"""
            <tr>
                <td><strong>{html.escape(str(item.get('code')))}</strong><br>{html.escape(str(item.get('name')))}</td>
                <td><strong style="color:{color};">{html.escape(str(item.get('decision')))}</strong></td>
                <td>{html.escape(str(item.get('layer_resonance_score', 0)))}</td>
                <td>{html.escape(str(item.get('execution_quality_score', 0)))}</td>
                <td>{yuan(item.get('capital'))}<br>{html.escape(str(item.get('shares')))}股</td>
                <td>{fmt(item.get('entry_low'))}-{fmt(item.get('entry_high'))}</td>
                <td>{fmt(item.get('take_profit_1'))}<br>{fmt(item.get('take_profit_2'))}</td>
                <td>{fmt(item.get('stop_loss'))}</td>
                <td>{html.escape(str(item.get('action')))}</td>
            </tr>
            """
        )

    option_line = "期权结论：今天没有必须模拟的合约；看不懂就不做。"
    if option_do_cards:
        first_option = option_do_cards[0]
        option_line = (
            f"期权只做仿真：{html.escape(str(first_option.get('code')))} "
            f"{html.escape(str(first_option.get('direction')))}，1张以内，"
            f"最大亏损约 {yuan(first_option.get('max_loss'))}。"
        )

    return f"""
    <div class="note" style="background:#fff8c5; border-left-color:#bf8700;">
        <h3 style="margin-top:0;">今日动作卡</h3>
        <strong>{summary}</strong><br>
        <span class="sub">数据闸门：{html.escape(str(coverage_gate.get('reason', '全市场覆盖状态未知。')))}</span><br>
        <span class="sub"><strong>战术现金调度：</strong>{html.escape(str(cash_decision.get('label')))}；本次允许转入 {yuan(cash_decision.get('allowed_transfer_amount'))}；总额 {yuan(cash_decision.get('tactical_callable_cash'))}。{html.escape(str(cash_decision.get('reason')))}</span><br>
        <span class="sub">可调动口径：场内资产 {yuan(cash_decision.get('on_exchange_asset_snapshot'))} + 战术现金 {yuan(cash_decision.get('tactical_callable_cash'))} = 总可调动约 {yuan(cash_decision.get('total_callable_capital'))}。</span><br>
        <span class="sub">这是把雷达翻译成可执行纪律：做/不做、买多少、哪里卖、哪里止损。</span>
        <table>
            <tr>
                <th>标的</th>
                <th>做/不做</th>
                <th>主线分</th>
                <th>执行分</th>
                <th>买多少</th>
                <th>买入区</th>
                <th>止盈</th>
                <th>止损</th>
                <th>小白解释</th>
            </tr>
            {''.join(stock_rows) if stock_rows else '<tr><td>--</td><td>不做</td><td>0</td><td>0</td><td>--</td><td>--</td><td>--</td><td>--</td><td>今日无合格短线动作。</td></tr>'}
        </table>
        <p><strong>星耀状态：</strong>{html.escape(xingyao_status_text(option_radar))}</p>
        <p><strong>期权/期货类：</strong>{option_line} 期货模块当前没有接入实盘数据，今天不做期货实盘。</p>
    </div>
    """


def yuan(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:,.0f}元"


def evaluate_strategy(item: Dict, portfolio: Dict) -> Dict:
    pos = position_map(portfolio).get(item["code"])
    if not pos or item.get("price") is None:
        return {
            "decision": "观察",
            "decision_level": "HOLD",
            "trade_amount": None,
            "position_value": None,
            "position_weight": None,
            "target_value": None,
            "gap_to_buy": None,
            "gap_to_sell": None,
            "reasons": ["未配置持仓/目标价，仅保留雷达观察"],
        }

    price = float(item["price"])
    shares = float(pos.get("shares") or 0)
    total_capital = float(portfolio.get("total_capital") or 0)
    cash = float(portfolio.get("cash") or 0)
    target_weight = float(pos.get("target_weight") or 0)
    max_single_weight = float(portfolio.get("max_single_weight") or 0.25)
    default_buy_amount = float(portfolio.get("default_buy_amount") or 10000)

    position_value = price * shares
    position_weight = position_value / total_capital if total_capital else 0
    target_value = total_capital * target_weight
    max_value = total_capital * max_single_weight
    buy_below = pos.get("buy_below")
    sell_above = pos.get("sell_above")
    stop_loss = pos.get("stop_loss")
    if buy_below is not None and float(buy_below) <= 0:
        buy_below = None

    reasons = []
    decision = "等待"
    decision_level = "HOLD"
    trade_amount = None

    if item["level"] == "RED":
        decision = "禁止买入"
        decision_level = "BLOCK"
        reasons.append("雷达红色，优先风控")
    elif stop_loss is not None and price <= float(stop_loss) and shares > 0:
        decision = "触发止损检查"
        decision_level = "SELL"
        trade_amount = position_value * 0.5
        reasons.append(f"价格 {price:.3f} <= 止损线 {float(stop_loss):.3f}")
    elif sell_above is not None and price >= float(sell_above) and shares > 0:
        decision = "分批止盈"
        decision_level = "SELL"
        trade_amount = position_value * 0.25
        reasons.append(f"价格 {price:.3f} >= 止盈线 {float(sell_above):.3f}")
    elif buy_below is not None and price <= float(buy_below):
        if position_value >= target_value:
            decision = "不加仓"
            reasons.append("已达到或超过目标仓位")
        elif position_value >= max_value:
            decision = "不加仓"
            reasons.append("已接近单只ETF仓位上限")
        elif cash <= 0:
            decision = "等待现金"
            reasons.append("现金配置不足")
        else:
            decision = "触发买入"
            decision_level = "BUY"
            trade_amount = min(default_buy_amount, target_value - position_value, max_value - position_value, cash)
            reasons.append(f"价格 {price:.3f} <= 买入线 {float(buy_below):.3f}")
    else:
        if buy_below is not None:
            gap = (price / float(buy_below) - 1) * 100
            reasons.append(f"距离买入线约 {gap:.2f}%")
        if sell_above is not None and shares > 0:
            gap = (float(sell_above) / price - 1) * 100
            reasons.append(f"距离止盈线约 {gap:.2f}%")

    if item["level"] == "YELLOW" and decision_level == "BUY":
        decision = "小仓买入/谨慎"
        reasons.append("雷达黄色，只允许小仓执行")

    if item["level"] == "RED" and pos.get("note"):
        reasons.append(str(pos["note"]))

    return {
        "decision": decision,
        "decision_level": decision_level,
        "trade_amount": trade_amount,
        "position_value": position_value,
        "position_weight": position_weight,
        "target_value": target_value,
        "gap_to_buy": ((price / float(buy_below) - 1) * 100) if buy_below else None,
        "gap_to_sell": ((float(sell_above) / price - 1) * 100) if sell_above and price else None,
        "reasons": reasons or ["未触发买卖条件，继续等待"],
    }


def trading_session_context(now: Optional[datetime] = None) -> Dict:
    now = now or datetime.now(BEIJING_TZ)
    current = now.strftime("%H:%M")
    if "09:00" <= current < "09:30":
        return {
            "label": "盘前预案",
            "next_decision_time": "09:40",
            "guidance": "只看候选和风险，不下单；9:40再看是否放量确认。",
        }
    if "09:30" <= current < "10:50":
        return {
            "label": "早盘确认",
            "next_decision_time": "10:45",
            "guidance": "只允许小仓试单；急拉超过5%默认不追，等二次确认。",
        }
    if "13:00" <= current < "14:30":
        return {
            "label": "午后延续",
            "next_decision_time": "14:40",
            "guidance": "检查上午强势是否延续；不把弱反弹当突破。",
        }
    if "14:30" <= current <= "15:10":
        return {
            "label": "尾盘处理",
            "next_decision_time": "收盘复盘",
            "guidance": "按计划决定止盈、止损或是否隔夜，不临时扩大仓位。",
        }
    return {
        "label": "复盘计划",
        "next_decision_time": "下个交易日09:10",
        "guidance": "整理候选池和纪律，不做盘后冲动决策。",
    }


def is_a_share_trading_day(now: Optional[datetime] = None) -> tuple[bool, str]:
    now = now or datetime.now(BEIJING_TZ)
    if wind_enabled():
        try:
            client = windpy_client()
            day = now.strftime("%Y-%m-%d")
            result = client.tdays(day, day, "")
            error_code = getattr(result, "ErrorCode", -1)
            dates = (getattr(result, "Data", None) or [[]])[0] if getattr(result, "Data", None) else []
            if error_code == 0:
                return bool(dates), "wind_tdays"
            logger.warning("Wind tdays failed: error=%s", error_code)
        except Exception as exc:
            logger.warning("Wind trading-day check failed: %s", exc)
    return now.weekday() < 5, "weekday_fallback"


def run_radar() -> Dict:
    high_risk_codes = split_env_set("ETF_HIGH_RISK_CODES", DEFAULT_HIGH_RISK_CODES)
    qdii_codes = split_env_set("ETF_QDII_CODES", DEFAULT_QDII_CODES)
    portfolio = load_portfolio()
    now = datetime.now(BEIJING_TZ)
    trading_day, trading_day_source = is_a_share_trading_day(now)

    if not trading_day:
        return {
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "session": {
                "label": "休市",
                "next_decision_time": "下个交易日09:10",
                "guidance": "休市，不生成动作卡。",
            },
            "watch_count": len(combined_watchlist()),
            "portfolio": portfolio,
            "results": [],
            "failures": [],
            "stock_radar": {"enabled": False, "results": [], "reason": "non-trading day"},
            "broad_market_scan": {"enabled": False, "results": [], "reason": "non-trading day"},
            "market_structure": {"enabled": False, "source": trading_day_source, "regime": "MARKET_CLOSED", "notes": ["A-share market closed."]},
            "market_structure_policy": {"enabled": False, "source": trading_day_source, "regime": "MARKET_CLOSED", "risk_level": "PAUSE", "notes": ["休市，不生成盘中动作卡。"]},
            "option_sim_radar": {"enabled": False, "results": [], "reason": "non-trading day"},
            "xingyao_data_status": {"enabled": False, "active_sources": [], "recommendation": "休市，未运行星耀探针。"},
            "coverage": {"etf_watch_count": len(combined_watchlist()), "coverage_note": f"Trading day check source: {trading_day_source}"},
            "trading_day": {"is_open": False, "source": trading_day_source},
            "action_stack": {
                "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "risk_gate": {"blocked": True, "level": "MARKET_CLOSED", "reason": "休市"},
                "short_term_cards": [],
                "option_cards": [],
            },
        }

    results = []
    failures = []
    watchlist = combined_watchlist()
    for code in watchlist:
        try:
            quote = fetch_quote(code)
            item = classify_quote(quote, high_risk_codes, qdii_codes)
            item["strategy"] = evaluate_strategy(item, portfolio)
            results.append(item)
            logger.info("%s %s checked", code, quote.name)
        except Exception as exc:
            logger.warning("ETF %s skipped: %s", code, exc)
            failures.append({"code": code, "error": str(exc)})

    stock_radar = run_stock_radar()
    for item in stock_radar.get("results", []):
        item["trade_plan"] = short_term_trade_plan(item, portfolio)
    broad_market_scan = run_broad_market_scan(load_digital_infra_watchlist())
    market_structure = load_market_structure()
    market_policy = market_structure_policy(market_structure)
    option_sim_radar = run_option_sim_radar()
    xingyao_data_status = run_xingyao_data_diagnostics(option_sim_radar)
    coverage = coverage_report(watchlist, stock_radar, broad_market_scan, option_sim_radar, xingyao_data_status)

    report = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "session": trading_session_context(now),
        "watch_count": len(watchlist),
        "portfolio": portfolio,
        "results": results,
        "failures": failures,
        "stock_radar": stock_radar,
        "broad_market_scan": broad_market_scan,
        "market_structure": market_structure,
        "market_structure_policy": market_policy,
        "option_sim_radar": option_sim_radar,
        "xingyao_data_status": xingyao_data_status,
        "coverage": coverage,
        "trading_day": {"is_open": True, "source": trading_day_source},
    }
    report["action_stack"] = build_action_stack(report)
    return report


def color_for(level: str) -> str:
    return {"GREEN": "#1a7f37", "YELLOW": "#9a6700", "RED": "#d1242f"}.get(level, "#57606a")


def label_for(level: str) -> str:
    return {"GREEN": "绿色", "YELLOW": "黄色", "RED": "红色"}.get(level, level)


def fmt(value, suffix: str = "", decimals: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:.{decimals}f}{suffix}"


def report_counts(report: Dict) -> Dict[str, int]:
    results = report.get("results", [])
    stock_results = report.get("stock_radar", {}).get("results", [])
    broad_results = report.get("broad_market_scan", {}).get("results", [])
    return {
        "green": sum(1 for item in results if item.get("level") == "GREEN"),
        "yellow": sum(1 for item in results if item.get("level") == "YELLOW"),
        "red": sum(1 for item in results if item.get("level") == "RED"),
        "failures": len(report.get("failures", [])),
        "stock_green": sum(1 for item in stock_results if item.get("level") == "GREEN"),
        "stock_yellow": sum(1 for item in stock_results if item.get("level") == "YELLOW"),
        "stock_red": sum(1 for item in stock_results if item.get("level") == "RED"),
        "broad_candidates": len(broad_results),
    }


def markdown_escape(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def build_report_metadata(report: Dict, subject: str) -> Dict:
    counts = report_counts(report)
    return {
        "subject": subject,
        "generated_at": report.get("generated_at"),
        "saved_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Shanghai",
        "watch_count": report.get("watch_count", 0),
        "green_count": counts["green"],
        "yellow_count": counts["yellow"],
        "red_count": counts["red"],
        "failure_count": counts["failures"],
        "source": "ETF Strategy Monitor",
        "disclaimer": "仅作交易纪律提醒，不构成投资建议。",
    }


def capital_plan_summary_lines(portfolio: Dict) -> List[str]:
    plan = portfolio.get("capital_plan") or {}
    if not plan:
        return []

    year_end = plan.get("year_end_2026_projection") or {}
    monthly_new = plan.get("monthly_new_money_plan") or {}
    off_assets = plan.get("off_platform_assets") or []
    allocation = plan.get("allocation_policy_for_strong_market") or {}
    deployment = plan.get("liquidity_deployment_plan") or {}
    tracks = plan.get("priority_ai_tracks") or []

    lines = [
        "",
        "## 年度资金计划",
        "",
        f"- 目标：{plan.get('objective', '未设置')}",
    ]
    if off_assets:
        asset = off_assets[0]
        lines.append(
            f"- 场外资产：{asset.get('name', '场外资产')} {yuan(asset.get('amount'))}，月现金流 {yuan(asset.get('current_monthly_cashflow'))}"
        )
    if monthly_new:
        lines.append(
            f"- 每月新增资金：{yuan(monthly_new.get('amount'))}，预计新增 {yuan(monthly_new.get('projected_new_money'))}"
        )
    if year_end:
        lines.extend(
            [
                f"- 年底基础资金：{yuan(year_end.get('base_before_market_profit'))}",
                f"- 强行情目标收益：{fmt((year_end.get('strong_market_target_return') or 0) * 100, '%')}，目标利润 {yuan(year_end.get('strong_market_target_profit_on_current_trading_capital'))}",
                f"- 强行情目标资金：{yuan(year_end.get('strong_market_target_capital'))}",
            ]
        )
    if allocation:
        lines.append(
            "- 仓位纪律：ETF核心 {core}；AI个股卫星 {satellite}；现金 {cash}；单只个股确认后上限 {single}".format(
                core=allocation.get("core_etf_weight_range", "未设置"),
                satellite=allocation.get("ai_stock_satellite_weight_range", "未设置"),
                cash=allocation.get("cash_buffer_weight_range", "未设置"),
                single=allocation.get("single_stock_confirmed_max_weight", "未设置"),
            )
        )
    if deployment:
        lines.extend(
            [
                "- 现金分层：阶段1主动资金 {active}；ETF核心目标 {core_target}；短线桶 {bucket}；单日新开仓上限 {daily_limit}".format(
                    active=yuan(deployment.get("stage_1_active_capital")),
                    core_target=yuan(deployment.get("stage_1_core_etf_target_value")),
                    bucket=yuan(deployment.get("stage_1_short_term_bucket")),
                    daily_limit=yuan(deployment.get("stage_1_max_new_buy_per_day")),
                ),
                f"- 外部活钱规则：{deployment.get('external_cash_transfer_rule', '')}",
                f"- 商铺本金规则：{deployment.get('shop_principal_rule', '')}",
            ]
        )
    if tracks:
        lines.append("- 优先主线：" + "、".join(str(item) for item in tracks))
    lines.append("- 纪律：30% 是强行情冲刺目标，不因目标不足反推重仓。")
    return lines


def short_term_pilot_summary_lines(portfolio: Dict) -> List[str]:
    pilot = (portfolio.get("capital_plan") or {}).get("short_term_pilot") or {}
    if not pilot or not pilot.get("enabled"):
        return []

    windows = pilot.get("time_windows") or []
    window_text = "；".join(
        f"{item.get('time')} {item.get('action')}" for item in windows if item.get("time")
    )
    bucket_text = ""
    if pilot.get("estimated_bucket_profit_if_3pct") is not None:
        bucket_text = (
            f"- 短线桶测算：若 {yuan(pilot.get('max_total_capital'))} 满仓整体涨3%约 "
            f"{yuan(pilot.get('estimated_bucket_profit_if_3pct'))}；涨5%约 "
            f"{yuan(pilot.get('estimated_bucket_profit_if_5pct'))}；亏3%约 "
            f"{yuan(pilot.get('estimated_bucket_loss_if_minus_3pct'))}"
        )
    return [
        "",
        "## 短线试运行",
        "",
        f"- 当前版本：{short_term_pilot_title(pilot)}",
        f"- 日目标/风控：目标 {yuan(pilot.get('daily_profit_target'))}；软熔断 {yuan(pilot.get('daily_loss_soft_stop'))}；硬熔断 {yuan(pilot.get('daily_loss_hard_stop'))}",
        f"- 资金：单只默认 {yuan(pilot.get('capital_per_stock'))}；强确认可到 {yuan(pilot.get('strong_signal_capital_per_stock'))}；最多 {pilot.get('max_stocks', 2)} 只；总额不超过 {yuan(pilot.get('max_total_capital'))}",
        "- 候选来源：每天由全市场扫描和主线共振生成；旧候选只作复盘参考，不再固定照抄。",
        f"- 测算：涨3%约 {yuan(pilot.get('estimated_profit_if_3pct'))}；涨5%约 {yuan(pilot.get('estimated_profit_if_5pct'))}；亏3%约 {yuan(pilot.get('estimated_loss_if_minus_3pct'))}",
        bucket_text,
        f"- 时间：{window_text}",
        "- 硬规则：9:10只看预案，9:40以后才允许小仓试单；错过第一波不是错误，追高才是错误。",
        "- A股T+1：当日买入的个股当天不能卖；每笔买入前先写好下一交易日的止盈/止损计划。",
    ]


def ifind_http_probe_summary() -> str:
    path = Path(IFIND_HTTP_PROBE_PATH)
    if not path.exists():
        return "iFind HTTP：未读取到探针文件；先不接入动作卡上游。"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"iFind HTTP：探针文件读取失败（{type(exc).__name__}），先不接入动作卡上游。"

    checks = payload.get("checks") or {}
    realtime_ok = bool((checks.get("realtime_quotes") or {}).get("ok"))
    basic_ok = bool((checks.get("basic_data") or {}).get("ok"))
    wencai_ok = bool((checks.get("wencai") or {}).get("ok"))
    generated = payload.get("generated_at") or "-"
    if realtime_ok and not (basic_ok and wencai_ok):
        return f"iFind HTTP：{generated} 实时报价已通，basic/wencai 未通；只做只读校验源。"
    if realtime_ok:
        return f"iFind HTTP：{generated} 探针通过；仍需20只样本与东方财富/券商页面双源校验。"
    return f"iFind HTTP：{generated} 实时报价未通过；不进入动作卡上游。"


def tomorrow_task_markdown_lines(report: Dict) -> List[str]:
    coverage = report.get("coverage", {}) or {}
    option_radar = report.get("option_sim_radar", {}) or {}
    source_counts = coverage.get("broad_source_counts", {})
    return [
        "",
        "## 明天要做",
        "",
        "- 09:20 先查 000725 京东方A 旧委托状态：待报、废单、已撤、已成或部分成交；状态不明先撤/确认。",
        "- 09:25 只看集合竞价；9:40 看承接。高于计划买入区间不让旧单自动追，必须重新算。",
        "- 催银河客户经理：期权仿真账号、官方行情端口、期权链导出/API、真实权利金、IV、Delta、Theta、成交量、持仓量。",
        "- 上交所期权资料：整理 ETF 期权规则、合约乘数、到期日、行权、保证金、风控和投资者教育材料。",
        "- 期权学习清单：书/论文/课程只进入证据池；重点沉淀方向判断、波动率判断、时间价值和最大亏损。",
        f"- 数据闸门：星耀基础合约 {option_radar.get('xingyao_contract_count', 0)} 条；不是实时盘口。{ifind_http_probe_summary()}",
        f"- 雷达刷新：全市场读取 {coverage.get('broad_rows_seen', 0)}/5000；来源行数 {source_counts}；明早重新跑，数据不新鲜就降级观察。",
    ]


def tomorrow_task_html(report: Dict) -> str:
    bullets = [line[2:] for line in tomorrow_task_markdown_lines(report) if line.startswith("- ")]
    return f"""
            <div class="note" style="background:#fff8e6; border-left-color:#d69a00;">
                <strong>明天要做</strong>
                <ul>
                    {''.join(f'<li>{html.escape(item)}</li>' for item in bullets)}
                </ul>
                <p>期权模块只训练判断：方向、波动率、时间价值、最大亏损和退出条件。没有真实期权链前，不给实盘建议。</p>
            </div>
    """


def capital_plan_html(portfolio: Dict) -> str:
    plan = portfolio.get("capital_plan") or {}
    if not plan:
        return ""

    year_end = plan.get("year_end_2026_projection") or {}
    monthly_new = plan.get("monthly_new_money_plan") or {}
    off_assets = plan.get("off_platform_assets") or []
    allocation = plan.get("allocation_policy_for_strong_market") or {}
    deployment = plan.get("liquidity_deployment_plan") or {}
    tracks = plan.get("priority_ai_tracks") or []
    asset_html = ""
    if off_assets:
        asset = off_assets[0]
        asset_html = (
            f"场外资产：{html.escape(str(asset.get('name', '场外资产')))} "
            f"{yuan(asset.get('amount'))}，月现金流 {yuan(asset.get('current_monthly_cashflow'))}<br>"
        )
    return f"""
            <div class="note" style="background:#fff8c5; border-left-color:#bf8700;">
                <strong>年度资金计划</strong><br>
                目标：{html.escape(str(plan.get('objective', '未设置')))}<br>
                {asset_html}
                每月新增：{yuan(monthly_new.get('amount'))}；年底基础资金：{yuan(year_end.get('base_before_market_profit'))}<br>
                强行情目标：{fmt((year_end.get('strong_market_target_return') or 0) * 100, '%')}；目标利润：{yuan(year_end.get('strong_market_target_profit_on_current_trading_capital'))}；目标资金：{yuan(year_end.get('strong_market_target_capital'))}<br>
                仓位纪律：ETF核心 {html.escape(str(allocation.get('core_etf_weight_range', '未设置')))}；AI个股卫星 {html.escape(str(allocation.get('ai_stock_satellite_weight_range', '未设置')))}；现金 {html.escape(str(allocation.get('cash_buffer_weight_range', '未设置')))}；单只确认上限 {html.escape(str(allocation.get('single_stock_confirmed_max_weight', '未设置')))}。<br>
                现金分层：阶段1主动资金 {yuan(deployment.get('stage_1_active_capital'))}；ETF核心目标 {yuan(deployment.get('stage_1_core_etf_target_value'))}；短线桶 {yuan(deployment.get('stage_1_short_term_bucket'))}；单日新开仓上限 {yuan(deployment.get('stage_1_max_new_buy_per_day'))}。<br>
                外部活钱规则：{html.escape(str(deployment.get('external_cash_transfer_rule', '未设置')))}<br>
                商铺本金规则：{html.escape(str(deployment.get('shop_principal_rule', '未设置')))}<br>
                优先主线：{html.escape('、'.join(str(item) for item in tracks))}
            </div>
    """


def short_term_pilot_html(portfolio: Dict) -> str:
    pilot = (portfolio.get("capital_plan") or {}).get("short_term_pilot") or {}
    if not pilot or not pilot.get("enabled"):
        return ""

    windows = pilot.get("time_windows") or []
    window_html = "<br>".join(
        f"{html.escape(str(item.get('time', '')))}：{html.escape(str(item.get('action', '')))}"
        for item in windows
    )
    hard_rules = pilot.get("hard_rules") or []
    hard_rule_html = "<br>".join(html.escape(str(rule)) for rule in hard_rules)
    if hard_rule_html:
        hard_rule_html += "<br>"
    hard_rule_html += "A股T+1：当日买入的个股当天不能卖；每笔买入前先写好下一交易日的止盈/止损计划。"
    bucket_html = ""
    if pilot.get("estimated_bucket_profit_if_3pct") is not None:
        bucket_html = (
            f"短线桶测算：若 {yuan(pilot.get('max_total_capital'))} 满仓整体涨3%约 "
            f"{yuan(pilot.get('estimated_bucket_profit_if_3pct'))}；涨5%约 "
            f"{yuan(pilot.get('estimated_bucket_profit_if_5pct'))}；亏3%约 "
            f"{yuan(pilot.get('estimated_bucket_loss_if_minus_3pct'))}。<br>"
        )

    return f"""
            <div class="note" style="background:#eaf5ff; border-left-color:#0969da;">
                <strong>短线试运行：{html.escape(short_term_pilot_title(pilot))}</strong><br>
                目标：{html.escape(str(pilot.get('goal', '先练执行，不追求大额盈利。')))}<br>
                日目标/风控：目标 {yuan(pilot.get('daily_profit_target'))}；软熔断 {yuan(pilot.get('daily_loss_soft_stop'))}；硬熔断 {yuan(pilot.get('daily_loss_hard_stop'))}。<br>
                资金：单只默认 {yuan(pilot.get('capital_per_stock'))}；强确认可到 {yuan(pilot.get('strong_signal_capital_per_stock'))}；最多 {html.escape(str(pilot.get('max_stocks', 2)))} 只；总额不超过 {yuan(pilot.get('max_total_capital'))}。<br>
                测算：涨3%约 {yuan(pilot.get('estimated_profit_if_3pct'))}；涨5%约 {yuan(pilot.get('estimated_profit_if_5pct'))}；亏3%约 {yuan(pilot.get('estimated_loss_if_minus_3pct'))}。<br>
                {bucket_html}
                <strong>候选来源</strong><br>每天由全市场扫描和主线共振生成；固定候选只作复盘参考，不再直接照抄进今日动作。<br>
                <strong>时间窗口</strong><br>{window_html}<br>
                <strong>硬规则</strong><br>{hard_rule_html}
            </div>
    """


def generate_markdown_report(report: Dict, subject: str) -> str:
    metadata = build_report_metadata(report, subject)
    portfolio = report.get("portfolio", {})
    session = report.get("session", {})
    upgrade_lines = [
        "## 系统升级状态",
        "",
        "- 已加入学习源 intake：Qbot、MilleXi stock_trading、czsc、SmartStock-AI-Kit、CCXT、BingoCrypto Dashboard、TradeMatcher、lightning-engine。",
        "- 已新增全系统集合文档：`docs/system_feature_collection_2026-06-02.md`。",
        "- 已新增全系统重跑邮件：主雷达、行动卡、纸面日志、学习源报告、公开网页抓取检查会合并成一封邮件。",
        "- 已加执行边界：撮合引擎和加密合约项目只做架构/UX学习，不接入 A 股/ETF 实盘链路。",
        "- 当前普通 ETF 雷达邮件也会显示本升级状态，避免只看到行情表而看不出系统版本。",
        "",
    ]
    lines = [
        f"# {subject}",
        "",
        "## 元数据",
        "",
        f"- 生成时间：{metadata['generated_at']} 北京时间",
        f"- 保存时间：{metadata['saved_at']} 北京时间",
        f"- 监控数量：{metadata['watch_count']}",
        f"- 绿色/黄色/红色：{metadata['green_count']} / {metadata['yellow_count']} / {metadata['red_count']}",
        f"- 数据缺口：{metadata['failure_count']}",
        "- 说明：仅作交易纪律提醒，不构成投资建议。",
        f"- 当前窗口：{session.get('label', '复盘计划')}；下一决策点：{session.get('next_decision_time', '下个交易日09:10')}；提示：{session.get('guidance', '')}",
        "",
        *upgrade_lines,
        "## 账户配置",
        "",
        f"- 总资金：{yuan(portfolio.get('total_capital'))}",
        f"- 现金：{yuan(portfolio.get('cash'))}",
        f"- 单只 ETF 上限：{fmt((portfolio.get('max_single_weight') or 0) * 100, '%')}",
        *capital_plan_summary_lines(portfolio),
        *short_term_pilot_summary_lines(portfolio),
        *action_plan_markdown_lines(report),
        *tomorrow_task_markdown_lines(report),
        "",
        "## 雷达结果",
        "",
        "| 代码 | 名称 | 最新价 | 涨跌幅 | 20日线 | 60日线 | 信号 | 动作 | 策略动作 | 金额 | 当前仓位 | 目标金额 | 原因 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]

    for item in report.get("results", []):
        strategy = item.get("strategy", {})
        position_weight = strategy.get("position_weight")
        reasons = "；".join(item.get("reasons", []))
        strategy_reasons = "；".join(strategy.get("reasons", []))
        lines.append(
            "| {code} | {name} | {price} | {pct} | {ma20} | {ma60} | {level} | {action} | {decision}<br>{strategy_reasons} | {amount} | {weight} | {target} | {reasons} |".format(
                code=markdown_escape(item.get("code")),
                name=markdown_escape(item.get("name")),
                price=fmt(item.get("price")),
                pct=fmt(item.get("pct_change"), "%"),
                ma20=fmt(item.get("ma20")),
                ma60=fmt(item.get("ma60")),
                level=label_for(item.get("level", "")),
                action=markdown_escape(item.get("action")),
                decision=markdown_escape(strategy.get("decision", "观察")),
                strategy_reasons=markdown_escape(strategy_reasons),
                amount=yuan(strategy.get("trade_amount")),
                weight=fmt(position_weight * 100 if position_weight is not None else None, "%"),
                target=yuan(strategy.get("target_value")),
                reasons=markdown_escape(reasons),
            )
        )

    option_radar = report.get("option_sim_radar", {})
    option_results = option_radar.get("results", [])
    if option_radar.get("enabled") and option_results:
        option_source_line = (
            f"- Data source: {option_radar.get('data_source', 'simulation')}; "
            f"Xingyao contracts: {option_radar.get('xingyao_contract_count', 0)}; "
            f"error: {option_radar.get('xingyao_error', '') or '-'}"
        )
        lines.extend(
            [
                "",
                option_source_line,
                "## 期权模拟雷达",
                "",
                f"- 标的 ETF：{' / '.join(load_option_etf_watchlist())}",
                f"- 合约乘数：{option_radar.get('contract_multiplier', 10000)} 份ETF/张；估算到期日：{option_radar.get('expiry')}；剩余约 {option_radar.get('days_to_expiry')} 天。",
                "- 说明：权利金为模拟估算，不是真实期权链报价；接入银河仿真盘后再替换为真实权利金、隐含波动率、Delta、Theta。",
                "- 纪律：只做模拟盘；先买方，不裸卖；单笔模拟权利金先按500-1500元练，不为了日入3000倒推杠杆。",
                "",
                "| ETF | 方向 | 行权价 | 到期日 | 权利金估算 | 盈亏平衡点 | 最大亏损/张 | ETF涨跌情景盈亏 | 时间价值风险 | 今日是否适合模拟 |",
                "| --- | --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |",
            ]
        )
        for item in option_results:
            scenario_text = "；".join(
                f"{scenario.get('move_pct'):+.0f}%:{yuan(scenario.get('profit'))}"
                for scenario in item.get("scenarios", [])
            )
            suitability_text = item.get("suitability")
            if item.get("xingyao_contract_code"):
                suitability_text = (
                    f"{suitability_text}; Xingyao: {item.get('xingyao_contract_code')} "
                    f"ref={fmt(item.get('xingyao_listing_ref_price'), decimals=4)}"
                )
            lines.append(
                "| {code} {name} | {direction} | {strike} | {expiry} | {premium} | {break_even} | {max_loss} | {scenarios} | {time_risk} | {suitability} |".format(
                    code=markdown_escape(item.get("code")),
                    name=markdown_escape(item.get("name")),
                    direction=markdown_escape(item.get("direction")),
                    strike=fmt(item.get("strike"), decimals=3),
                    expiry=markdown_escape(item.get("expiry")),
                    premium=fmt(item.get("premium"), decimals=4),
                    break_even=fmt(item.get("break_even"), decimals=4),
                    max_loss=yuan(item.get("max_loss")),
                    scenarios=markdown_escape(scenario_text),
                    time_risk=markdown_escape(item.get("time_risk")),
                    suitability=markdown_escape(suitability_text),
                )
            )

    coverage = report.get("coverage", {})
    if coverage:
        lines.extend(
            [
                "",
                "## 覆盖检查",
                "",
                f"- ETF重点监控：{coverage.get('etf_watch_count', 0)} 只；代码：{' / '.join(coverage.get('etf_watchlist', []))}",
                f"- 期权ETF模拟：{' / '.join(coverage.get('option_etf_watchlist', []))}；生成 {coverage.get('option_rows', 0)} 行认购/认沽情景。",
                f"- AI主题个股池：{coverage.get('ai_stock_watch_count', 0)} 只。",
                f"- A股全市场扫描：本次读取 {coverage.get('broad_rows_seen', 0)} 行；过滤后候选 {coverage.get('broad_candidates', 0)} 只；扫描容量预算 {coverage.get('broad_scan_capacity', 0)} 行。",
                f"- 数据源轮动：{', '.join(coverage.get('broad_scan_sources', []))}；来源行数 {coverage.get('broad_source_counts', {})}；估算缺口 {coverage.get('broad_missing_estimate', 0)} 行。",
                f"- 星耀实用状态：活跃源 {coverage.get('xingyao_active_sources', [])}；快照行数 {coverage.get('xingyao_snapshot_rows', 0)}；K线行数 {coverage.get('xingyao_kline_rows', 0)}。",
                f"- 星耀建议：{coverage.get('xingyao_recommendation', '')}",
                f"- 覆盖说明：{coverage.get('coverage_note', '')}",
            ]
        )

    xingyao_status = report.get("xingyao_data_status", {})
    if xingyao_status:
        lines.extend(["", "## 星耀数智用透检查", ""])
        for item in xingyao_status.get("matrix", []):
            lines.append(
                "- {module}: {status}；接口 {api}；行数 {rows}；{note}".format(
                    module=markdown_escape(item.get("module")),
                    status=markdown_escape(item.get("status")),
                    api=markdown_escape(item.get("sdk_api")),
                    rows=item.get("rows", 0),
                    note=markdown_escape(item.get("note")),
                )
            )
        capabilities = xingyao_status.get("capabilities") or {}
        lines.append(
            f"- SDK能力：AmazingData={capabilities.get('amazingdata_import')}；TGW={capabilities.get('tgw_import')}；TGW方法={capabilities.get('tgw_methods', [])}。"
        )
        if capabilities.get("sdk_error"):
            lines.append(f"- SDK错误：{markdown_escape(capabilities.get('sdk_error'))}")

    stock_radar = report.get("stock_radar", {})
    stock_results = stock_radar.get("results", [])
    if stock_radar.get("enabled") and stock_results:
        lines.extend(
            [
                "",
                "## AI 产业链个股观察",
                "",
                f"- 个股扫描数量：{stock_radar.get('watch_count', 0)}",
                "- 说明：个股只做卫星仓候选发现；A级/B级只是仓位纪律提示，不构成投资建议。",
                "",
                "| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 20日线 | 60日线 | 信号 | 动作 | 短线档位 | 建议上限 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | --- |",
            ]
        )
        for item in display_stock_results(stock_results):
            reasons = "；".join(item.get("reasons", []))
            trade_plan = item.get("trade_plan") or {}
            lines.append(
                "| {code} | {name} | {layer} | {price} | {pct} | {ma20} | {ma60} | {level} | {action} | {tier} | {capital} | {reasons}；{plan_reason} |".format(
                    code=markdown_escape(item.get("code")),
                    name=markdown_escape(item.get("name")),
                    layer=markdown_escape(item.get("layer_name")),
                    price=fmt(item.get("price")),
                    pct=fmt(item.get("pct_change"), "%"),
                    ma20=fmt(item.get("ma20")),
                    ma60=fmt(item.get("ma60")),
                    level=label_for(item.get("level", "")),
                    action=markdown_escape(item.get("action")),
                    tier=markdown_escape(trade_plan.get("tier", "观察")),
                    capital=yuan(trade_plan.get("capital")),
                    reasons=markdown_escape(reasons),
                    plan_reason=markdown_escape(trade_plan.get("reason", "")),
                )
            )

    broad_scan = report.get("broad_market_scan", {})
    broad_results = broad_scan.get("results", [])
    if broad_scan.get("enabled") and broad_results:
        market_structure = report.get("market_structure", {})
        structure_policy = report.get("market_structure_policy") or market_structure_policy(market_structure)
        tiers = broad_market_tiers(broad_results, portfolio, market_structure)
        short_term_policy = short_term_policy_sentence(portfolio)
        coverage_gate = broad_market_coverage_gate(report)
        lines.extend(
            [
                "",
                "## iFind市场结构层",
                "",
                f"- 来源：{markdown_escape(structure_policy.get('source'))}；日期：{markdown_escape(structure_policy.get('as_of'))}；状态：{markdown_escape(structure_policy.get('regime'))} / {markdown_escape(structure_policy.get('risk_level'))}。",
                f"- 追高阈值：{fmt(structure_policy.get('chase_limit_pct'), '%')}；强势行业：{markdown_escape(' / '.join((structure_policy.get('preferred_industries') or [])[:5]))}。",
                f"- 弱势行业降级：{markdown_escape(' / '.join((structure_policy.get('avoid_industries') or [])[:8]))}。",
                *[f"- {markdown_escape(note)}" for note in (structure_policy.get("notes") or [])],
                "",
                "## 全市场短线雷达",
                "",
                f"- 扫描A股数量：{broad_scan.get('scanned_count', 0)}；过滤后候选：{broad_scan.get('candidate_count', len(broad_results))}。",
                "- 默认买入池仅筛沪深主板，避开创业板/科创/北交权限问题；创业板/科创可观察，但不作为当前下单候选。",
                f"- 结构：强度榜用于看风格；观察池用于明天盯盘；{short_term_policy}",
                "- 纪律：候选池只用于盯盘；没有进入“今日动作卡=做”的标的，一律不买。全市场异动备选必须降级观察，没有9:40放量、板块强度和盘口承接就空手。",
                "",
                "### 全市场强度榜 Top 50",
                "",
                "- 系统看的强弱排序，不等于买入。",
                "",
                "| 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | 成交额 | 量比 | 换手 | 动作 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for item in tiers["strength"]:
            reasons = "；".join(item.get("reasons", []))
            lines.append(
                "| {code} | {name} | {industry} | {price} | {pct} | {amount} | {vr} | {turnover} | {action} | {reasons} |".format(
                    code=markdown_escape(item.get("code")),
                    name=markdown_escape(item.get("name")),
                    industry=markdown_escape(item.get("industry")),
                    price=fmt(item.get("price")),
                    pct=fmt(item.get("pct_change"), "%"),
                    amount=yuan(item.get("amount")),
                    vr=fmt(item.get("volume_ratio")),
                    turnover=fmt(item.get("turnover"), "%"),
                    action=markdown_escape(item.get("action")),
                    reasons=markdown_escape(reasons),
                )
            )
        lines.extend(
            [
                "",
                "### 今日观察池 Top 10",
                "",
                "- 给你明天早盘重点看，不要求全部下单。",
                "",
                "| 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | 成交额 | 量比 | 换手 | 动作 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for item in tiers["watch"]:
            reasons = "；".join(item.get("reasons", []))
            lines.append(
                "| {code} | {name} | {industry} | {price} | {pct} | {amount} | {vr} | {turnover} | {action} | {reasons} |".format(
                    code=markdown_escape(item.get("code")),
                    name=markdown_escape(item.get("name")),
                    industry=markdown_escape(item.get("industry")),
                    price=fmt(item.get("price")),
                    pct=fmt(item.get("pct_change"), "%"),
                    amount=yuan(item.get("amount")),
                    vr=fmt(item.get("volume_ratio")),
                    turnover=fmt(item.get("turnover"), "%"),
                    action=markdown_escape(item.get("action")),
                    reasons=markdown_escape(reasons),
                )
            )
        lines.extend(
            [
                "",
                f"### 今日观察候选池（非动作卡）1-{short_term_pilot_policy(portfolio).get('max_stocks', 3)}只",
                "",
                "- 数据覆盖达标时才允许进入短线试单；仍然必须等9:40放量、板块强度和盘口承接确认。",
                f"- 当前数据闸门：{coverage_gate.get('reason', '全市场覆盖状态未知。')}",
                "",
                "| 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | 成交额 | 量比 | 换手 | 动作 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        action_items = [] if coverage_gate.get("blocked") else tiers["actionable"]
        if action_items:
            for item in action_items:
                reasons = "；".join(item.get("reasons", []))
                lines.append(
                    "| {code} | {name} | {industry} | {price} | {pct} | {amount} | {vr} | {turnover} | {action} | {reasons} |".format(
                        code=markdown_escape(item.get("code")),
                        name=markdown_escape(item.get("name")),
                        industry=markdown_escape(item.get("industry")),
                        price=fmt(item.get("price")),
                        pct=fmt(item.get("pct_change"), "%"),
                        amount=yuan(item.get("amount")),
                        vr=fmt(item.get("volume_ratio")),
                        turnover=fmt(item.get("turnover"), "%"),
                        action=markdown_escape(item.get("action")),
                        reasons=markdown_escape(reasons),
                    )
                )
        else:
            reason = coverage_gate.get("reason") if coverage_gate.get("blocked") else "没有通过成交额/量比/涨幅/换手综合过滤"
            lines.append(f"| -- | 今日无合格可操作池 | -- | -- | -- | -- | -- | -- | 空手 | {markdown_escape(reason)} |")

    ai_summary = report.get("ai_summary")
    if ai_summary:
        lines.extend(["", "## AI 策略简报", "", str(ai_summary).strip()])

    if report.get("failures"):
        lines.extend(["", "## 数据缺口", ""])
        for item in report["failures"]:
            lines.append(f"- {item.get('code')}: {item.get('error')}")

    lines.extend(["", "## 原始 JSON", "", "同目录 `.json` 文件保存了机器可读数据，适合后续做趋势分析。", ""])
    return "\n".join(lines)


def save_report_archive(report: Dict, subject: str) -> Dict[str, str]:
    report_root = Path(REPORTS_DIR)
    month_dir = report_root / datetime.now(BEIJING_TZ).strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d_%H%M%S")
    base_name = f"{stamp}_etf_radar"
    md_path = month_dir / f"{base_name}.md"
    json_path = month_dir / f"{base_name}.json"

    payload = {
        "metadata": build_report_metadata(report, subject),
        "session": report.get("session", {}),
        "portfolio": report.get("portfolio", {}),
        "results": report.get("results", []),
        "stock_radar": report.get("stock_radar", {}),
        "broad_market_scan": report.get("broad_market_scan", {}),
        "market_structure": report.get("market_structure", {}),
        "market_structure_policy": report.get("market_structure_policy", {}),
        "option_sim_radar": report.get("option_sim_radar", {}),
        "xingyao_data_status": report.get("xingyao_data_status", {}),
        "action_stack": report.get("action_stack", {}),
        "coverage": report.get("coverage", {}),
        "failures": report.get("failures", []),
        "ai_summary": report.get("ai_summary", ""),
    }
    if isinstance(payload.get("action_stack"), dict):
        payload["action_stack"]["generated_at"] = report.get("generated_at")

    markdown = generate_markdown_report(report, subject)
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_root / "latest.md").write_text(markdown, encoding="utf-8")
    (report_root / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("Report archive saved: %s and %s", md_path, json_path)
    return {"markdown": str(md_path), "json": str(json_path)}


def generate_html_email(report: Dict) -> str:
    ai_summary = report.get("ai_summary", "")
    session = report.get("session", {})
    report_generated_at = (
        report.get("generated_at")
        or (report.get("metadata") or {}).get("generated_at")
        or "-"
    )

    upgrade_html = """
        <div class="upgrade">
            <h3>系统升级状态</h3>
            <ul>
                <li><strong>学习源已扩展：</strong>Qbot、MilleXi stock_trading、czsc、SmartStock-AI-Kit、CCXT、BingoCrypto Dashboard、TradeMatcher、lightning-engine。</li>
                <li><strong>新增系统全集文档：</strong><code>docs/system_feature_collection_2026-06-02.md</code>。</li>
                <li><strong>新增全系统重跑邮件：</strong>主雷达、行动卡、纸面日志、学习源报告、公开网页抓取检查会合并成一封邮件。</li>
                <li><strong>执行边界已加固：</strong>撮合引擎和加密合约项目只做架构/UX学习，不接入 A 股/ETF 实盘链路。</li>
                <li><strong>普通 ETF 雷达邮件已升级：</strong>现在也会显示这段状态，避免只看到行情表而看不出系统版本。</li>
            </ul>
        </div>
    """

    rows = []
    for item in report["results"]:
        reasons = "<br>".join(html.escape(reason) for reason in item["reasons"])
        strategy = item.get("strategy", {})
        strategy_reasons = "<br>".join(html.escape(reason) for reason in strategy.get("reasons", []))
        level_color = color_for(item["level"])
        decision_level = strategy.get("decision_level", "HOLD")
        decision_color = {
            "BUY": "#1a7f37",
            "SELL": "#d1242f",
            "BLOCK": "#d1242f",
            "HOLD": "#9a6700",
        }.get(decision_level, "#57606a")
        position_weight = strategy.get("position_weight")
        target_value = strategy.get("target_value")
        rows.append(
            f"""
            <tr>
                <td><strong>{html.escape(item['code'])}</strong><br>{html.escape(item['name'])}</td>
                <td>{fmt(item['price'])}</td>
                <td>{fmt(item['pct_change'], '%')}</td>
                <td>{fmt(item['ma20'])}</td>
                <td>{fmt(item['ma60'])}</td>
                <td><span style="color:{level_color}; font-weight:bold;">{label_for(item['level'])}</span><br>{html.escape(item['action'])}</td>
                <td>
                    <strong style="color:{decision_color};">{html.escape(strategy.get('decision', '观察'))}</strong><br>
                    金额：{yuan(strategy.get('trade_amount'))}<br>
                    当前仓位：{fmt(position_weight * 100 if position_weight is not None else None, '%')}<br>
                    目标金额：{yuan(target_value)}<br>
                    <span style="color:#57606a;">{strategy_reasons}</span>
                </td>
                <td>{reasons}</td>
            </tr>
            """
        )

    stock_rows = []
    stock_radar = report.get("stock_radar", {})
    for item in display_stock_results(stock_radar.get("results", [])):
        reasons = "<br>".join(html.escape(reason) for reason in item.get("reasons", []))
        trade_plan = item.get("trade_plan") or {}
        level_color = color_for(item["level"])
        stock_rows.append(
            f"""
            <tr>
                <td><strong>{html.escape(item['code'])}</strong><br>{html.escape(item['name'])}</td>
                <td>{html.escape(item.get('layer_name') or '')}</td>
                <td>{fmt(item['price'])}</td>
                <td>{fmt(item['pct_change'], '%')}</td>
                <td>{fmt(item['ma20'])}</td>
                <td>{fmt(item['ma60'])}</td>
                <td><span style="color:{level_color}; font-weight:bold;">{label_for(item['level'])}</span><br>{html.escape(item['action'])}</td>
                <td><strong>{html.escape(str(trade_plan.get('tier', '观察')))}</strong><br>上限：{yuan(trade_plan.get('capital'))}<br>{html.escape(str(trade_plan.get('reason', '')))}</td>
                <td>{reasons}</td>
            </tr>
            """
        )

    stock_html = ""
    if stock_rows:
        stock_html = f"""
        <h3>AI 产业链个股观察</h3>
        <div class="sub">
            扫描 {stock_radar.get('watch_count', 0)} 只个股；用于发现存算一体、存储、光模块、AI芯片、服务器等主线扩散。个股只做卫星仓候选，不构成投资建议。
        </div>
        <table>
            <tr>
                <th>个股</th>
                <th>层级</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>20日线</th>
                <th>60日线</th>
                <th>信号</th>
                <th>短线档位</th>
                <th>原因</th>
            </tr>
            {''.join(stock_rows)}
        </table>
        """

    option_radar = report.get("option_sim_radar", {})
    option_rows = []
    for item in option_radar.get("results", []):
        scenario_text = "<br>".join(
            f"{scenario.get('move_pct'):+.0f}%：{yuan(scenario.get('profit'))}"
            for scenario in item.get("scenarios", [])
        )
        xingyao_hint = ""
        if item.get("xingyao_contract_code"):
            xingyao_hint = (
                f"<br><span class=\"sub\">Xingyao: {html.escape(str(item.get('xingyao_contract_code')))} "
                f"ref={fmt(item.get('xingyao_listing_ref_price'), decimals=4)}</span>"
            )
        option_rows.append(
            f"""
            <tr>
                <td><strong>{html.escape(item.get('code', ''))}</strong><br>{html.escape(item.get('name', ''))}</td>
                <td>{html.escape(item.get('direction', ''))}</td>
                <td>{fmt(item.get('strike'), decimals=3)}</td>
                <td>{html.escape(str(item.get('expiry', '')))}<br>{html.escape(str(item.get('days_to_expiry', '')))}天</td>
                <td>{fmt(item.get('premium'), decimals=4)}<br>{yuan(item.get('contract_cost'))}/张</td>
                <td>{fmt(item.get('break_even'), decimals=4)}</td>
                <td>{yuan(item.get('max_loss'))}</td>
                <td>{scenario_text}</td>
                <td>{html.escape(item.get('time_risk', ''))}</td>
                <td>{html.escape(item.get('suitability', ''))}{xingyao_hint}</td>
            </tr>
            """
        )

    option_html = ""
    if option_rows:
        option_html = f"""
        <h3>期权模拟雷达</h3>
        <div class="sub">
            Data source: {html.escape(str(option_radar.get('data_source', 'simulation')))}；
            Xingyao contracts: {html.escape(str(option_radar.get('xingyao_contract_count', 0)))}；
            error: {html.escape(str(option_radar.get('xingyao_error', '') or '-'))}<br>
            标的 ETF：{html.escape(' / '.join(load_option_etf_watchlist()))}。
            合约乘数：{html.escape(str(option_radar.get('contract_multiplier', 10000)))} 份ETF/张；
            估算到期日：{html.escape(str(option_radar.get('expiry', '')))}；
            剩余约 {html.escape(str(option_radar.get('days_to_expiry', '')))} 天。<br>
            权利金为模拟估算，不是真实期权链报价；接入银河仿真盘后再替换为真实权利金、隐含波动率、Delta、Theta。
            只做模拟盘；先买方，不裸卖；单笔模拟权利金先按500-1500元练。
        </div>
        <table>
            <tr>
                <th>ETF</th>
                <th>方向</th>
                <th>行权价</th>
                <th>到期日</th>
                <th>权利金</th>
                <th>盈亏平衡点</th>
                <th>最大亏损</th>
                <th>ETF涨跌情景盈亏</th>
                <th>时间价值风险</th>
                <th>是否适合今天模拟</th>
            </tr>
            {''.join(option_rows)}
        </table>
        """

    coverage = report.get("coverage", {})
    coverage_html = ""
    if coverage:
        coverage_html = f"""
        <div class="note" style="background:#f6f8fa; border-left-color:#57606a;">
            <strong>覆盖检查</strong><br>
            ETF重点监控：{html.escape(str(coverage.get('etf_watch_count', 0)))} 只；
            代码：{html.escape(' / '.join(coverage.get('etf_watchlist', [])))}<br>
            期权ETF模拟：{html.escape(' / '.join(coverage.get('option_etf_watchlist', [])))}；
            生成 {html.escape(str(coverage.get('option_rows', 0)))} 行认购/认沽情景。<br>
            AI主题个股池：{html.escape(str(coverage.get('ai_stock_watch_count', 0)))} 只。<br>
            A股全市场扫描：本次读取 {html.escape(str(coverage.get('broad_rows_seen', 0)))} 行；
            过滤后候选 {html.escape(str(coverage.get('broad_candidates', 0)))} 只；
            扫描容量预算 {html.escape(str(coverage.get('broad_scan_capacity', 0)))} 行。<br>
            数据源轮动：{html.escape(', '.join(coverage.get('broad_scan_sources', [])))}；
            来源行数 {html.escape(str(coverage.get('broad_source_counts', {})))}；
            估算缺口 {html.escape(str(coverage.get('broad_missing_estimate', 0)))} 行。<br>
            {html.escape(str(coverage.get('coverage_note', '')))}
        </div>
        """

    broad_scan = report.get("broad_market_scan", {})
    portfolio = report.get("portfolio", {})
    market_structure = report.get("market_structure", {})
    structure_policy = report.get("market_structure_policy") or market_structure_policy(market_structure)
    broad_tiers = broad_market_tiers(broad_scan.get("results", []), portfolio, market_structure)
    short_term_policy = short_term_policy_sentence(portfolio)
    coverage_gate = broad_market_coverage_gate(report)

    def render_broad_table_rows(items: List[Dict]) -> str:
        rows = []
        for item in items:
            reasons = "<br>".join(html.escape(reason) for reason in item.get("reasons", []))
            rows.append(
                f"""
                <tr>
                    <td><strong>{html.escape(item['code'])}</strong><br>{html.escape(item['name'])}</td>
                    <td>{html.escape(item.get('industry') or '')}</td>
                    <td>{fmt(item['price'])}</td>
                    <td>{fmt(item['pct_change'], '%')}</td>
                    <td>{yuan(item.get('amount'))}</td>
                    <td>{fmt(item.get('volume_ratio'))}</td>
                    <td>{fmt(item.get('turnover'), '%')}</td>
                    <td>{html.escape(item.get('action') or '')}</td>
                    <td>{reasons}</td>
                </tr>
                """
            )
        return "".join(rows)

    broad_html = ""
    if broad_tiers["strength"]:
        actionable_rows = "" if coverage_gate.get("blocked") else render_broad_table_rows(broad_tiers["actionable"])
        if not actionable_rows:
            no_action_reason = html.escape(str(coverage_gate.get("reason") if coverage_gate.get("blocked") else "没有通过成交额/量比/涨幅/换手综合过滤"))
            actionable_rows = """
                <tr>
                    <td><strong>--</strong><br>今日无合格可操作池</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>空手</td>
                    <td>__NO_ACTION_REASON__</td>
                </tr>
            """.replace("__NO_ACTION_REASON__", no_action_reason)
        broad_html = f"""
        <h3>全市场短线雷达</h3>
        <div class="note" style="background:#fff8e6; border-left-color:#d69a00;">
            <strong>iFind市场结构层：</strong>
            {html.escape(str(structure_policy.get('regime') or '-'))} /
            {html.escape(str(structure_policy.get('risk_level') or '-'))}；
            追高阈值 {fmt(structure_policy.get('chase_limit_pct'), '%')}；
            强势行业 {html.escape(' / '.join((structure_policy.get('preferred_industries') or [])[:5]))}；
            弱势行业 {html.escape(' / '.join((structure_policy.get('avoid_industries') or [])[:6]))}。
        </div>
        <div class="sub">
            扫描A股 {broad_scan.get('scanned_count', 0)} 只；过滤后候选 {broad_scan.get('candidate_count', len(broad_tiers["strength"]))} 只。
            强度榜用于看风格，观察池用于明天盯盘，{html.escape(short_term_policy)}
            候选池只用于盯盘；只有“今日动作卡=做”的标的才允许进入人工确认。全市场异动备选必须降级观察。
        </div>
        <h4>全市场强度榜 Top 50</h4>
        <div class="sub">系统看的强弱排序，不等于买入。</div>
        <table>
            <tr>
                <th>个股</th>
                <th>行业</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交额</th>
                <th>量比</th>
                <th>换手</th>
                <th>动作</th>
                <th>原因</th>
            </tr>
            {render_broad_table_rows(broad_tiers["strength"])}
        </table>
        <h4>今日观察池 Top 10</h4>
        <div class="sub">给你明天早盘重点看，不要求全部下单。</div>
        <table>
            <tr>
                <th>个股</th>
                <th>行业</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交额</th>
                <th>量比</th>
                <th>换手</th>
                <th>动作</th>
                <th>原因</th>
            </tr>
            {render_broad_table_rows(broad_tiers["watch"])}
        </table>
        <h4>今日观察候选池（非动作卡）1-{html.escape(str(short_term_pilot_policy(portfolio).get('max_stocks', 3)))}只</h4>
        <div class="sub">这里不是买入指令；只有“今日动作卡=做”的标的才允许进入人工确认。当前数据闸门：{html.escape(str(coverage_gate.get('reason', '全市场覆盖状态未知。')))}</div>
        <table>
            <tr>
                <th>个股</th>
                <th>行业</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交额</th>
                <th>量比</th>
                <th>换手</th>
                <th>动作</th>
                <th>原因</th>
            </tr>
            {actionable_rows}
        </table>
        """

    failure_html = ""
    if report["failures"]:
        items = "".join(
            f"<li>{html.escape(item['code'])}: {html.escape(item['error'])}</li>"
            for item in report["failures"]
        )
        failure_html = f"""
        <div class="note">
            <strong>数据缺口</strong>
            <ul>{items}</ul>
            <p>数据源临时失败时，本次任务不会报错退出，避免无意义失败邮件。</p>
        </div>
        """

    ai_html = ""
    if ai_summary:
        ai_html = f"""
        <div class="ai">
            <h3>AI 策略简报</h3>
            <div style="white-space: pre-wrap;">{html.escape(ai_summary)}</div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, "Microsoft YaHei", sans-serif; color: #24292f; line-height: 1.55; }}
            .container {{ max-width: 980px; margin: 0 auto; padding: 20px; }}
            h2 {{ margin-bottom: 6px; }}
            .sub {{ color: #57606a; margin-bottom: 18px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
            th, td {{ border-bottom: 1px solid #d8dee4; padding: 10px; vertical-align: top; text-align: left; }}
            th {{ background: #f6f8fa; }}
            .note {{ margin-top: 18px; padding: 12px; border-left: 4px solid #bf8700; background: #fff8c5; }}
            .upgrade {{ margin-top: 18px; padding: 14px; border-left: 4px solid #0969da; background: #eaf5ff; }}
            .upgrade h3 {{ margin-top: 0; margin-bottom: 8px; }}
            .upgrade ul {{ margin: 0; padding-left: 20px; }}
            .upgrade li {{ margin: 5px 0; }}
            .ai {{ margin-top: 18px; padding: 14px; border-left: 4px solid #8250df; background: #f6f8fa; }}
            .footer {{ margin-top: 20px; color: #6e7781; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>ETF Strategy Monitor</h2>
            <div class="sub">生成时间：{html.escape(str(report_generated_at))} 北京时间。仅作交易纪律提醒，不构成投资建议。</div>
            {upgrade_html}
            <div class="note" style="background:#eaf5ff; border-left-color:#0969da;">
                <strong>{html.escape(str(session.get('label', '复盘计划')))}</strong><br>
                下一决策点：{html.escape(str(session.get('next_decision_time', '下个交易日09:10')))}<br>
                {html.escape(str(session.get('guidance', '整理候选池和纪律，不做冲动决策。')))}
            </div>
            <div class="note" style="background:#f6f8fa; border-left-color:#57606a;">
                <strong>账户配置</strong><br>
                总资金：{yuan(report.get('portfolio', {}).get('total_capital'))}；
                现金：{yuan(report.get('portfolio', {}).get('cash'))}；
                单只ETF上限：{fmt((report.get('portfolio', {}).get('max_single_weight') or 0) * 100, '%')}。
            </div>
            {capital_plan_html(report.get('portfolio', {}))}
            {short_term_pilot_html(report.get('portfolio', {}))}
            {action_plan_html(report)}
            {tomorrow_task_html(report)}
            <table>
                <tr>
                    <th>标的</th>
                    <th>最新价</th>
                    <th>涨跌幅</th>
                    <th>20日线</th>
                    <th>60日线</th>
                    <th>信号</th>
                    <th>策略动作</th>
                    <th>原因</th>
                </tr>
                {''.join(rows)}
            </table>
            {option_html}
            {coverage_html}
            {stock_html}
            {broad_html}
            {ai_html}
            {failure_html}
            <div class="footer">
                规则：绿色=可研究小仓或按网格执行；黄色=观察不追；红色=禁止追买。513310 默认作为高溢价风险样本处理。
            </div>
        </div>
    </body>
    </html>
    """


def main() -> bool:
    send_monitor_email = env_enabled("MONITOR_SEND_EMAIL", "true")
    sender_email = os.getenv("SENDER_EMAIL", "")
    sender_password = os.getenv("SENDER_PASSWORD", "")
    recipient_email = os.getenv("RECIPIENT_EMAIL", "")

    if send_monitor_email and (not sender_email or not sender_password or not recipient_email):
        logger.error("Missing email secrets: SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL")
        return False

    logger.info("=== ETF Strategy Monitor started ===")
    report = run_radar()
    report["ai_summary"] = generate_ai_summary(report)

    if not report["results"]:
        logger.warning("No ETF data available. Skipping email but returning success.")
        save_report_archive(report, f"ETF雷达：无可用数据 - {report['generated_at']}")
        return True

    counts = report_counts(report)
    session_label = report.get("session", {}).get("label", "雷达")
    subject = f"ETF雷达[{session_label}]：绿色{counts['green']}个 / 红色{counts['red']}个 - {report['generated_at']}"
    html_content = generate_html_email(report)
    save_report_archive(report, subject)

    if not send_monitor_email:
        logger.info("ETF strategy monitor email skipped by MONITOR_SEND_EMAIL=false")
        return True

    notifier = EmailNotifier(
        sender_email=sender_email,
        sender_password=sender_password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
    )

    if notifier.send_html_alert(recipient_email, subject, html_content):
        logger.info("ETF strategy email sent")
        return True

    logger.error("ETF strategy email failed")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
