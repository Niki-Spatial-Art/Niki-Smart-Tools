#!/usr/bin/env python3
"""ETF Strategy Monitor.

This script checks a focused ETF watchlist, labels each ETF as green/yellow/red,
adds an optional AI summary, and sends a short email report.
"""

import html
import contextlib
import io
import json
import logging
import os
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
PORTFOLIO_FILE = os.getenv("PORTFOLIO_FILE", "portfolio.json")
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")
DIGITAL_INFRA_FILE = os.getenv("DIGITAL_INFRA_FILE", "digital_infra_watchlist.json")


def env_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


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


def fetch_quote(code: str) -> Quote:
    sources = [
        ("eastmoney", fetch_quote_eastmoney),
        ("tencent", fetch_quote_tencent),
        ("sina", fetch_quote_sina),
    ]
    errors = []
    for source_name, fetcher in sources:
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


def fetch_xingyao_option_basic_rows() -> Dict:
    """Fetch ETF option basic info from Galaxy AmazingData when configured locally."""
    if not env_enabled("XINGYAO_ENABLED", "false"):
        return {"enabled": False, "source": "simulation", "contracts": [], "error": "disabled"}

    username = os.getenv("XINGYAO_USER", "").strip()
    password = os.getenv("XINGYAO_PASSWORD", "").strip()
    if not username or not password:
        return {"enabled": False, "source": "simulation", "contracts": [], "error": "missing credentials"}

    for sdk_path in xingyao_sdk_paths():
        if sdk_path and os.path.exists(sdk_path) and sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)

    try:
        import AmazingData as ad  # type: ignore
    except Exception as exc:
        return {"enabled": False, "source": "simulation", "contracts": [], "error": f"import failed: {exc}"}

    host = os.getenv("XINGYAO_HOST", "101.230.159.234")
    port = int(os.getenv("XINGYAO_PORT", "8600"))
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ok = ad.login(username=username, password=password, host=host, port=port)
        if not ok:
            return {"enabled": False, "source": "simulation", "contracts": [], "error": "login failed"}

        base = ad.BaseData()
        info = ad.InfoData()
        option_codes = base.get_option_code_list("EXTRA_ETF_OP")
        option_info = info.get_option_basic_info(option_codes, is_local=False)
        contracts = option_info.to_dict("records") if hasattr(option_info, "to_dict") else []
        return {
            "enabled": True,
            "source": "xingyao_basic",
            "contracts": contracts,
            "contract_count": len(contracts),
            "option_code_count": len(option_codes),
            "error": "",
        }
    except Exception as exc:
        logger.warning("Xingyao option basic fetch failed: %s", exc)
        return {"enabled": False, "source": "simulation", "contracts": [], "error": str(exc)}
    finally:
        with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ad.logout()


def xingyao_contract_for(option_rows: List[Dict], etf_code: str, direction: str, strike: float, expiry: str) -> Optional[Dict]:
    contract_type = "C" if direction == "认购" else "P"
    expiry_key = expiry.replace("-", "")[:6]
    candidates = []
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
        candidates.append((abs(row_strike - strike), row))
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
        timeout=int(os.getenv("BROAD_MARKET_PAGE_TIMEOUT_SECONDS", "4")),
        retries=int(os.getenv("BROAD_MARKET_PAGE_RETRIES", "1")),
    ).get("data") or {}
    return data.get("diff") or []


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
        "score": score,
        "action": "候选，等回踩/二次确认",
        "reasons": reasons,
    }


def run_broad_market_scan(watchlist: Dict) -> Dict:
    if not env_enabled("BROAD_MARKET_SCAN_ENABLED", "true"):
        return {"enabled": False, "results": [], "failures": []}

    max_pages = int(os.getenv("BROAD_MARKET_MAX_PAGES", "28"))
    page_size = int(os.getenv("BROAD_MARKET_PAGE_SIZE", "200"))
    time_budget = float(os.getenv("BROAD_MARKET_TIME_BUDGET_SECONDS", "110"))
    layer_index = layer_index_from_watchlist(watchlist)
    candidates = []
    failures = []
    seen_codes = set()
    total_rows_seen = 0
    started_at = time.monotonic()

    for page in range(1, max_pages + 1):
        elapsed = time.monotonic() - started_at
        if elapsed >= time_budget:
            failures.append({"page": page, "error": f"broad market scan time budget reached after {elapsed:.1f}s"})
            break
        try:
            rows = fetch_market_snapshot_page(page, page_size)
            if not rows:
                break
            total_rows_seen += len(rows)
            for row in rows:
                item = classify_market_candidate(row, layer_index)
                if not item or item["code"] in seen_codes:
                    continue
                seen_codes.add(item["code"])
                candidates.append(item)
        except Exception as exc:
            logger.warning("broad market page %s skipped: %s", page, exc)
            failures.append({"page": page, "error": str(exc)})
            if len(failures) >= 3:
                break

    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    max_results = int(os.getenv("BROAD_MARKET_MAX_RESULTS", "50"))
    return {
        "enabled": True,
        "scan_pages": max_pages,
        "scanned_count": total_rows_seen,
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
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        logger.info("No portfolio config found, strategy actions will be skipped")
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
        with open(DIGITAL_INFRA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
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


def coverage_report(watchlist: List[str], stock_radar: Dict, broad_market_scan: Dict, option_sim_radar: Dict) -> Dict:
    max_pages = int(os.getenv("BROAD_MARKET_MAX_PAGES", "28"))
    page_size = int(os.getenv("BROAD_MARKET_PAGE_SIZE", "200"))
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
        "broad_scan_capacity": max_pages * page_size,
        "broad_rows_seen": broad_market_scan.get("scanned_count", 0),
        "broad_candidates": broad_market_scan.get("candidate_count", 0),
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
    max_codes = int(os.getenv("AI_STOCK_MAX_CODES", "130"))
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


def broad_market_tiers(results: List[Dict], portfolio: Optional[Dict] = None) -> Dict[str, List[Dict]]:
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

    actionable = []
    for item in results:
        pct = item.get("pct_change")
        amount = item.get("amount")
        volume_ratio = item.get("volume_ratio")
        turnover = item.get("turnover")
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
        action_item = dict(item)
        board = item.get("board") or board_label(str(item.get("code", "")))
        if board != "沪深主板":
            action_item["action"] = f"{board}观察，先确认权限和20cm波动风险"
            reason_prefix = f"已扫描到{board}标的，但当前只作为全市场观察，不直接纳入默认下单池"
        elif item.get("theme_layers"):
            action_item["action"] = "主线可操作候选，限9:40二次确认后小仓"
            reason_prefix = "通过主线短线过滤：命中主题层，且涨幅不过热、成交额够、量比放大、换手未失控"
        else:
            action_item["action"] = "全市场异动备选，需降级观察"
            reason_prefix = "通过全市场量价过滤，但未命中当前AI/数字基建主线；只能作为备选，不优先下单"
        action_item["reasons"] = [
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


def run_radar() -> Dict:
    high_risk_codes = split_env_set("ETF_HIGH_RISK_CODES", DEFAULT_HIGH_RISK_CODES)
    qdii_codes = split_env_set("ETF_QDII_CODES", DEFAULT_QDII_CODES)
    portfolio = load_portfolio()

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
    option_sim_radar = run_option_sim_radar()
    coverage = coverage_report(watchlist, stock_radar, broad_market_scan, option_sim_radar)

    now = datetime.now(BEIJING_TZ)
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "session": trading_session_context(now),
        "watch_count": len(watchlist),
        "portfolio": portfolio,
        "results": results,
        "failures": failures,
        "stock_radar": stock_radar,
        "broad_market_scan": broad_market_scan,
        "option_sim_radar": option_sim_radar,
        "coverage": coverage,
    }


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

    candidates = pilot.get("candidate_codes") or []
    candidate_text = "、".join(
        f"{item.get('code')} {item.get('name')}" for item in candidates if item.get("code")
    )
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
        f"- 日期：{pilot.get('pilot_date', '未设置')}；阶段：{pilot.get('stage', '熟悉度测试')}",
        f"- 日目标/风控：目标 {yuan(pilot.get('daily_profit_target'))}；软熔断 {yuan(pilot.get('daily_loss_soft_stop'))}；硬熔断 {yuan(pilot.get('daily_loss_hard_stop'))}",
        f"- 资金：单只默认 {yuan(pilot.get('capital_per_stock'))}；强确认可到 {yuan(pilot.get('strong_signal_capital_per_stock'))}；最多 {pilot.get('max_stocks', 2)} 只；总额不超过 {yuan(pilot.get('max_total_capital'))}",
        f"- 候选：{candidate_text}",
        f"- 测算：涨3%约 {yuan(pilot.get('estimated_profit_if_3pct'))}；涨5%约 {yuan(pilot.get('estimated_profit_if_5pct'))}；亏3%约 {yuan(pilot.get('estimated_loss_if_minus_3pct'))}",
        bucket_text,
        f"- 时间：{window_text}",
        "- 硬规则：9:10只看预案，9:40以后才允许小仓试单；错过第一波不是错误，追高才是错误。",
    ]


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

    candidates = pilot.get("candidate_codes") or []
    candidate_html = "<br>".join(
        "{code} {name}：{theme}；{entry}".format(
            code=html.escape(str(item.get("code", ""))),
            name=html.escape(str(item.get("name", ""))),
            theme=html.escape(str(item.get("theme", ""))),
            entry=html.escape(str(item.get("entry_rule", ""))),
        )
        for item in candidates
    )
    windows = pilot.get("time_windows") or []
    window_html = "<br>".join(
        f"{html.escape(str(item.get('time', '')))}：{html.escape(str(item.get('action', '')))}"
        for item in windows
    )
    hard_rules = pilot.get("hard_rules") or []
    hard_rule_html = "<br>".join(html.escape(str(rule)) for rule in hard_rules)
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
                <strong>短线试运行：{html.escape(str(pilot.get('pilot_date', '未设置')))} {html.escape(str(pilot.get('stage', '熟悉度测试')))}</strong><br>
                目标：{html.escape(str(pilot.get('goal', '先练执行，不追求大额盈利。')))}<br>
                日目标/风控：目标 {yuan(pilot.get('daily_profit_target'))}；软熔断 {yuan(pilot.get('daily_loss_soft_stop'))}；硬熔断 {yuan(pilot.get('daily_loss_hard_stop'))}。<br>
                资金：单只默认 {yuan(pilot.get('capital_per_stock'))}；强确认可到 {yuan(pilot.get('strong_signal_capital_per_stock'))}；最多 {html.escape(str(pilot.get('max_stocks', 2)))} 只；总额不超过 {yuan(pilot.get('max_total_capital'))}。<br>
                测算：涨3%约 {yuan(pilot.get('estimated_profit_if_3pct'))}；涨5%约 {yuan(pilot.get('estimated_profit_if_5pct'))}；亏3%约 {yuan(pilot.get('estimated_loss_if_minus_3pct'))}。<br>
                {bucket_html}
                <strong>候选</strong><br>{candidate_html}<br>
                <strong>时间窗口</strong><br>{window_html}<br>
                <strong>硬规则</strong><br>{hard_rule_html}
            </div>
    """


def generate_markdown_report(report: Dict, subject: str) -> str:
    metadata = build_report_metadata(report, subject)
    portfolio = report.get("portfolio", {})
    session = report.get("session", {})
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
        "## 账户配置",
        "",
        f"- 总资金：{yuan(portfolio.get('total_capital'))}",
        f"- 现金：{yuan(portfolio.get('cash'))}",
        f"- 单只 ETF 上限：{fmt((portfolio.get('max_single_weight') or 0) * 100, '%')}",
        *capital_plan_summary_lines(portfolio),
        *short_term_pilot_summary_lines(portfolio),
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
                f"- 覆盖说明：{coverage.get('coverage_note', '')}",
            ]
        )

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
        tiers = broad_market_tiers(broad_results, portfolio)
        short_term_policy = short_term_policy_sentence(portfolio)
        lines.extend(
            [
                "",
                "## 全市场短线雷达",
                "",
                f"- 扫描A股数量：{broad_scan.get('scanned_count', 0)}；过滤后候选：{broad_scan.get('candidate_count', len(broad_results))}。",
                "- 默认买入池仅筛沪深主板，避开创业板/科创/北交权限问题；创业板/科创可观察，但不作为当前下单候选。",
                f"- 结构：强度榜用于看风格；观察池用于明天盯盘；{short_term_policy}",
                "- 纪律：优先主线可操作候选；全市场异动备选必须降级观察，没有9:40放量、板块强度和盘口承接就空手。",
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
                f"### 今日可操作池 1-{short_term_pilot_policy(portfolio).get('max_stocks', 3)}只",
                "",
                "- 仅代表具备短线试单条件；仍然必须等9:40放量、板块强度和盘口承接确认。",
                "",
                "| 代码 | 名称 | 行业 | 最新价 | 涨跌幅 | 成交额 | 量比 | 换手 | 动作 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        action_items = tiers["actionable"]
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
            lines.append("| -- | 今日无合格可操作池 | -- | -- | -- | -- | -- | -- | 空手 | 没有通过成交额/量比/涨幅/换手综合过滤 |")

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
        "option_sim_radar": report.get("option_sim_radar", {}),
        "coverage": report.get("coverage", {}),
        "failures": report.get("failures", []),
        "ai_summary": report.get("ai_summary", ""),
    }

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
            {html.escape(str(coverage.get('coverage_note', '')))}
        </div>
        """

    broad_scan = report.get("broad_market_scan", {})
    portfolio = report.get("portfolio", {})
    broad_tiers = broad_market_tiers(broad_scan.get("results", []), portfolio)
    short_term_policy = short_term_policy_sentence(portfolio)

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
        actionable_rows = render_broad_table_rows(broad_tiers["actionable"])
        if not actionable_rows:
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
                    <td>没有通过成交额/量比/涨幅/换手综合过滤</td>
                </tr>
            """
        broad_html = f"""
        <h3>全市场短线雷达</h3>
        <div class="sub">
            扫描A股 {broad_scan.get('scanned_count', 0)} 只；过滤后候选 {broad_scan.get('candidate_count', len(broad_tiers["strength"]))} 只。
            强度榜用于看风格，观察池用于明天盯盘，{html.escape(short_term_policy)}
            优先主线可操作候选；全市场异动备选必须降级观察。
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
        <h4>今日可操作池 1-{html.escape(str(short_term_pilot_policy(portfolio).get('max_stocks', 3)))}只</h4>
        <div class="sub">仅代表具备短线试单条件；仍然必须等9:40放量、板块强度和盘口承接确认。</div>
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
            .ai {{ margin-top: 18px; padding: 14px; border-left: 4px solid #8250df; background: #f6f8fa; }}
            .footer {{ margin-top: 20px; color: #6e7781; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>ETF Strategy Monitor</h2>
            <div class="sub">生成时间：{html.escape(report['generated_at'])} 北京时间。仅作交易纪律提醒，不构成投资建议。</div>
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
    sender_email = os.getenv("SENDER_EMAIL", "")
    sender_password = os.getenv("SENDER_PASSWORD", "")
    recipient_email = os.getenv("RECIPIENT_EMAIL", "")

    if not sender_email or not sender_password or not recipient_email:
        logger.error("Missing email secrets: SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL")
        return False

    logger.info("=== ETF Strategy Monitor started ===")
    report = run_radar()
    report["ai_summary"] = generate_ai_summary(report)

    if not report["results"]:
        logger.warning("No ETF data available. Skipping email but returning success.")
        save_report_archive(report, f"ETF雷达：无可用数据 - {report['generated_at']}")
        return True

    notifier = EmailNotifier(
        sender_email=sender_email,
        sender_password=sender_password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
    )

    counts = report_counts(report)
    session_label = report.get("session", {}).get("label", "雷达")
    subject = f"ETF雷达[{session_label}]：绿色{counts['green']}个 / 红色{counts['red']}个 - {report['generated_at']}"
    html_content = generate_html_email(report)
    save_report_archive(report, subject)

    if notifier.send_html_alert(recipient_email, subject, html_content):
        logger.info("ETF strategy email sent")
        return True

    logger.error("ETF strategy email failed")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
