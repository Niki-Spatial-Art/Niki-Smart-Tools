#!/usr/bin/env python3
"""ETF Strategy Monitor.

This script checks a focused ETF watchlist, labels each ETF as green/yellow/red,
adds an optional AI summary, and sends a short email report.
"""

import html
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    "510300",  # CSI 300 ETF
    "510500",  # CSI 500 ETF
    "512100",  # CSI 1000 ETF
    "512880",  # Securities ETF
    "588000",  # STAR 50 ETF
    "512760",  # Semiconductor ETF
    "513180",  # Hang Seng Tech ETF
    "518880",  # Gold ETF
]

DEFAULT_HIGH_RISK_CODES = {"513310"}
DEFAULT_QDII_CODES = {"513310", "159696", "513180"}
PORTFOLIO_FILE = os.getenv("PORTFOLIO_FILE", "portfolio.json")
REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")


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


def eastmoney_get(url: str, params: Dict, timeout: int = 18) -> Dict:
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

    for attempt in range(3):
        for candidate in urls:
            try:
                response = requests.get(candidate, params=params, headers=headers, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_exc = exc
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
    price = safe_float(data.get("f43"), 1000)
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
        ).get("data") or {}
        klines = data.get("klines") or []
        closes = [float(item.split(",")[2]) for item in klines if len(item.split(",")) > 2]
        ma20 = mean(closes[-20:]) if len(closes) >= 20 else None
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else None
        return ma20, ma60
    except Exception as exc:
        logger.warning("Failed to fetch moving averages for %s: %s", code, exc)
        return None, None


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


def position_map(portfolio: Dict) -> Dict[str, Dict]:
    return {str(item.get("code")): item for item in portfolio.get("positions", [])}


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

    return {
        "generated_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "watch_count": len(watchlist),
        "portfolio": portfolio,
        "results": results,
        "failures": failures,
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
    return {
        "green": sum(1 for item in results if item.get("level") == "GREEN"),
        "yellow": sum(1 for item in results if item.get("level") == "YELLOW"),
        "red": sum(1 for item in results if item.get("level") == "RED"),
        "failures": len(report.get("failures", [])),
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


def generate_markdown_report(report: Dict, subject: str) -> str:
    metadata = build_report_metadata(report, subject)
    portfolio = report.get("portfolio", {})
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
        "",
        "## 账户配置",
        "",
        f"- 总资金：{yuan(portfolio.get('total_capital'))}",
        f"- 现金：{yuan(portfolio.get('cash'))}",
        f"- 单只 ETF 上限：{fmt((portfolio.get('max_single_weight') or 0) * 100, '%')}",
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
        "portfolio": report.get("portfolio", {}),
        "results": report.get("results", []),
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
            <div class="note" style="background:#f6f8fa; border-left-color:#57606a;">
                <strong>账户配置</strong><br>
                总资金：{yuan(report.get('portfolio', {}).get('total_capital'))}；
                现金：{yuan(report.get('portfolio', {}).get('cash'))}；
                单只ETF上限：{fmt((report.get('portfolio', {}).get('max_single_weight') or 0) * 100, '%')}。
            </div>
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
    subject = f"ETF雷达：绿色{counts['green']}个 / 红色{counts['red']}个 - {report['generated_at']}"
    html_content = generate_html_email(report)
    save_report_archive(report, subject)

    if notifier.send_html_alert(recipient_email, subject, html_content):
        logger.info("ETF strategy email sent")
        return True

    logger.error("ETF strategy email failed")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
