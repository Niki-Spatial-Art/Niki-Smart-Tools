#!/usr/bin/env python3
"""ETF Strategy Monitor.

This script checks a focused ETF watchlist, labels each ETF as green/yellow/red,
adds an optional AI summary, and sends a short email report.
"""

import html
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Dict, List, Optional

import pytz
import requests

from ai_client import generate_ai_summary
from emailer import EmailNotifier


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


def safe_float(value, scale: float = 1.0) -> Optional[float]:
    try:
        if value in (None, "-", ""):
            return None
        return float(value) / scale
    except (TypeError, ValueError):
        return None


def eastmoney_get(url: str, params: Dict, timeout: int = 12) -> Dict:
    headers = {
        "User-Agent": "Mozilla/5.0 ETF Strategy Monitor",
        "Referer": "https://quote.eastmoney.com/",
    }
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_quote(code: str) -> Quote:
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


def run_radar() -> Dict:
    high_risk_codes = split_env_set("ETF_HIGH_RISK_CODES", DEFAULT_HIGH_RISK_CODES)
    qdii_codes = split_env_set("ETF_QDII_CODES", DEFAULT_QDII_CODES)

    results = []
    failures = []
    for code in load_watchlist():
        try:
            quote = fetch_quote(code)
            results.append(classify_quote(quote, high_risk_codes, qdii_codes))
            logger.info("%s %s checked", code, quote.name)
        except Exception as exc:
            logger.warning("ETF %s skipped: %s", code, exc)
            failures.append({"code": code, "error": str(exc)})

    return {
        "generated_at": datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "watch_count": len(load_watchlist()),
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


def generate_html_email(report: Dict) -> str:
    ai_summary = generate_ai_summary(report)

    rows = []
    for item in report["results"]:
        reasons = "<br>".join(html.escape(reason) for reason in item["reasons"])
        level_color = color_for(item["level"])
        rows.append(
            f"""
            <tr>
                <td><strong>{html.escape(item['code'])}</strong><br>{html.escape(item['name'])}</td>
                <td>{fmt(item['price'])}</td>
                <td>{fmt(item['pct_change'], '%')}</td>
                <td>{fmt(item['ma20'])}</td>
                <td>{fmt(item['ma60'])}</td>
                <td><span style="color:{level_color}; font-weight:bold;">{label_for(item['level'])}</span><br>{html.escape(item['action'])}</td>
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
            <table>
                <tr>
                    <th>标的</th>
                    <th>最新价</th>
                    <th>涨跌幅</th>
                    <th>20日线</th>
                    <th>60日线</th>
                    <th>信号</th>
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

    if not report["results"]:
        logger.warning("No ETF data available. Skipping email but returning success.")
        return True

    notifier = EmailNotifier(
        sender_email=sender_email,
        sender_password=sender_password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
    )

    red_count = sum(1 for item in report["results"] if item["level"] == "RED")
    green_count = sum(1 for item in report["results"] if item["level"] == "GREEN")
    subject = f"ETF雷达：绿色{green_count}个 / 红色{red_count}个 - {report['generated_at']}"
    html_content = generate_html_email(report)

    if notifier.send_html_alert(recipient_email, subject, html_content):
        logger.info("ETF strategy email sent")
        return True

    logger.error("ETF strategy email failed")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
