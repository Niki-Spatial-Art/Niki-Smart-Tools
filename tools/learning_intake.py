"""Build a daily learning and decision-support report for the local quant desk."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emailer import EmailNotifier


ROOT = Path(__file__).resolve().parents[1]
LEARNING_REPORT = ROOT / "reports" / "learning_intake.md"
IFIND_CLEAN_DIR = ROOT / "reports" / "ifind_clean"
BACKTEST_GLOB = "ifind_position_backtest_*.json"
FACTOR_DOCS = [
    ROOT / "docs" / "factor_research_playbook_2026-06-04.md",
    ROOT / "docs" / "quant_methodology_source_triage_2026-06-04.md",
    ROOT / "docs" / "level2_informed_trading_proxy_2026-06-04.md",
    ROOT / "docs" / "self_evolving_skill_stock_selection_2026-06-04.md",
    ROOT / "docs" / "ai_quant_methodology_intake_2026-06-04.md",
]


def load_sources(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_local_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def latest_ifind_clean_radar_path() -> Path:
    rows = sorted(IFIND_CLEAN_DIR.glob("*_ifind_clean_radar.json"), key=lambda p: p.stat().st_mtime)
    return rows[-1] if rows else IFIND_CLEAN_DIR / "ifind_clean_radar_missing.json"


def latest_backtest_path() -> Path:
    rows = sorted((ROOT / "reports").glob(BACKTEST_GLOB), key=lambda p: p.stat().st_mtime)
    return rows[-1] if rows else ROOT / "reports" / "ifind_position_backtest_missing.json"


def github_slug(url: str) -> str | None:
    match = re.search(r"github\.com/([^/\s]+/[^/\s#?]+)", url)
    if not match:
        return None
    return match.group(1).removesuffix(".git")


def fetch_github_meta(url: str, timeout: int = 12) -> dict[str, Any]:
    slug = github_slug(url)
    if not slug:
        return {}
    api_url = f"https://api.github.com/repos/{slug}"
    response = requests.get(api_url, headers={"Accept": "application/vnd.github+json"}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return {
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "updated_at": data.get("updated_at"),
        "description": data.get("description") or "",
        "language": data.get("language") or "",
        "license": (data.get("license") or {}).get("spdx_id") or "",
    }


def concise_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc)
    if isinstance(exc, requests.RequestException):
        return f"{name}: metadata unavailable; run again with network access"
    return f"{name}: {text[:120]}"


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def pct(value: float, is_ratio: bool = False) -> str:
    if value is None or math.isnan(value):
        return "-"
    number = value * 100 if is_ratio else value
    return f"{number:.2f}%"


def price(value: float) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def shorten(text: str, limit: int = 34) -> str:
    raw = " ".join(str(text or "").split())
    return raw if len(raw) <= limit else raw[: limit - 1] + "…"


def score_source(source: dict[str, Any], keywords: list[str], meta: dict[str, Any]) -> tuple[int, list[str]]:
    haystack = " ".join(
        [
            source.get("name", ""),
            source.get("type", ""),
            source.get("why_watch", ""),
            source.get("url", ""),
            meta.get("description", ""),
            meta.get("language", ""),
        ]
    ).lower()
    hits = [keyword for keyword in keywords if keyword.lower() in haystack]
    score = len(hits) * 2
    if source.get("type") == "github":
        score += 2
    if (meta.get("stars") or 0) >= 5000:
        score += 2
    if meta.get("updated_at", "")[:4] >= "2025":
        score += 1
    if "risk" in haystack or "backtest" in haystack:
        score += 2
    return score, hits


def next_action_for(source: dict[str, Any], score: int, hits: list[str]) -> str:
    source_type = source.get("type")
    if source_type == "community":
        return "只记录反复出现的坑点，不把社区观点直接变成交易动作。"
    if score >= 8:
        return "保留高优先级，下周只做一个小实验，不并行开太多坑。"
    if hits:
        return "保留观察，先读文档和样例，再决定是否接入。"
    return "低优先级归档，除非后面出现明确使用场景。"


def decision_support_for(source: dict[str, Any], hits: list[str]) -> str:
    text = " ".join(
        [
            source.get("name", ""),
            source.get("type", ""),
            source.get("why_watch", ""),
            " ".join(hits),
        ]
    ).lower()
    if "ifind" in text or "data connector" in text or "akshare" in text or "openbb" in text:
        return "提高数据接入与字段校验，减少盘中缺字段。"
    if "backtest" in text or "vectorbt" in text or "qlib" in text or "quantconnect" in text:
        return "把动作卡转成胜率、回撤和触发条件。"
    if "risk" in text or "portfolio" in text or "quantstats" in text:
        return "辅助仓位、回撤、止损线和隔夜风险判断。"
    if "options" in text or "volatility" in text or "vn.py" in text:
        return "辅助期权/波动率框架与仿真复盘。"
    if "dashboard" in text or "workflow" in text or "agent" in text or "financial services" in text:
        return "优化动作卡、人机确认、T+1检查与盘中提示。"
    if source.get("type") == "community":
        return "收集坑点，变成待验证问题，不直接影响买卖。"
    return "先做资料库，不进盘中决策。"


def classify_strong_watch(item: dict[str, Any]) -> bool:
    return as_float(item.get("shares"), 0) <= 0 and as_float(item.get("trend_score"), -99) >= 2 and as_float(item.get("dist_ma20"), -999) > 0


def short_reason(item: dict[str, Any], bt: dict[str, Any]) -> str:
    reasons = []
    sim = bt.get("similar_backtest") or {}
    if not bt:
        reasons.append("还没有稳定回测覆盖")
    if as_float(item.get("change")) >= 5:
        reasons.append("当天已经急拉")
    if as_float(item.get("ret20")) >= 20:
        reasons.append("20日涨幅偏大")
    if as_float(item.get("dist_ma20")) >= 8:
        reasons.append("离MA20偏远")
    if int(as_float(sim.get("sample"), 0)) < 8:
        reasons.append("样本偏少")
    if bt and as_float(sim.get("next1_win_rate")) < 0.55:
        reasons.append("1日胜率不够")
    if bt and as_float(sim.get("next2_median")) <= 0:
        reasons.append("2日中位数不支持")
    return "；".join(reasons) or "继续观察，等更清楚的承接信号"


def line_for_backtest(item: dict[str, Any], bt: dict[str, Any], conclusion: str) -> str:
    code = str(item.get("code") or bt.get("code") or "-")
    name = item.get("name") or code
    sim = bt.get("similar_backtest") or {}
    return (
        f"{code} {name}：{conclusion}。"
        f"样本 {int(as_float(sim.get('sample'), 0))}；"
        f"1日胜率 {pct(as_float(sim.get('next1_win_rate')), True)}；"
        f"2日中位 {pct(as_float(sim.get('next2_median')), True)}；"
        f"20日涨幅 {pct(as_float(item.get('ret20')))}；"
        f"离MA20 {pct(as_float(item.get('dist_ma20')))}。"
    )


def factor_intake_lines() -> list[str]:
    existing = [path for path in FACTOR_DOCS if path.exists()]
    status = "；".join(path.name for path in existing) if existing else "尚未找到 2026-06-04 因子资料文档"
    return [
        f"资料来源：已读取昨天的因子报告和 github11 粘贴资料沉淀文档。覆盖文件：{status}。",
        "录入结论：这些资料进入研究层和动作卡验证层，不直接生成买入信号。",
        "P1 立刻纳入：因子验证四件套、交易直觉因子化、华泰自进化 Skill 选股、风格因子轮动。",
        "P2 代理验证：广发 Level2 知情交易因子。当前没有 Level2，只能用 iFind 量比、成交额 5/20、MA20 距离、20日回撤、同主题强势数做代理。",
        "P3 中长期研究：CrossAttention 混频因子、Prophet + XGBoost、LLM 基本面文本解析。它们适合周/月频和研究报告，不进盘中短线买点。",
        "进入动作卡门槛：样本数、T+1/T+2/T+5 收益、胜率、中位收益、追高过滤、风控闸门都通过后，才允许从观察卡升级为买入候选。",
        "禁止项：研报标题、社区观点、单次高胜率、无 Level2 的大单叙事，都不能直接写成买入动作。",
    ]


def build_plain_report(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    strong_watch: list[dict[str, Any]],
    buy_candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    no_buy: list[tuple[dict[str, Any], dict[str, Any]]],
    covered_count: int,
    bt_by_code: dict[str, dict[str, Any]],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_action = "有条件等回踩买" if buy_candidates else "没有默认新开仓，先等"
    lines = [
        "# 简洁学习报告",
        "",
        f"生成时间：{now}",
        "",
        "## 今日总览",
        f"旧仓优先处理 {len(holdings)} 只。强势观察 {len(strong_watch)} 只。已回测覆盖 {covered_count} 只。明日新开仓结论：{default_action}。",
        "",
        "## 今天先做什么",
        f"第一，先处理旧仓。共有 {len(holdings)} 只，先看止损、减压和反弹处理，不因为月目标硬开新风险。",
        f"第二，再看强势观察。共有 {len(strong_watch)} 只，只允许看回测覆盖后的观察票。",
        f"第三，新开仓默认：{default_action}。没有 clean radar 和回测同时支持，就不把它写成买入动作。",
        "",
        "## 明日新开仓",
    ]
    if buy_candidates:
        for item, bt in buy_candidates[:6]:
            code = str(item.get("code") or "")
            sim = bt.get("similar_backtest") or {}
            lines.append(
                f"{code} {item.get('name') or code}：等回踩买，不追高，不高开直冲。"
                f"观察位看 {price(as_float(bt.get('rebound_line')))} 附近承接；"
                f"样本 {int(as_float(sim.get('sample'), 0))}；"
                f"1日胜率 {pct(as_float(sim.get('next1_win_rate')), True)}；"
                f"2日中位 {pct(as_float(sim.get('next2_median')), True)}。"
            )
    else:
        lines.append("没有默认可买的新票。这个结论不是说永远不买，是说当前样本和位置不支持盘中硬追。")

    lines.extend(["", "## 强势观察复盘"])
    if strong_watch:
        buy_codes = {str(item.get("code") or "") for item, _ in buy_candidates}
        for item in strong_watch[:10]:
            code = str(item.get("code") or "")
            bt = bt_by_code.get(code) or {}
            if code in buy_codes:
                conclusion = "等回踩买"
            elif bt:
                conclusion = "不买"
            else:
                conclusion = "未回测，不纳入默认下单池"
            lines.append(line_for_backtest(item, bt, conclusion))
            if conclusion != "等回踩买":
                lines.append(f"不买原因：{short_reason(item, bt)}。")
    else:
        lines.append("当前没有强势观察票。")

    lines.extend(["", "## 没有买的票也怎么学习"])
    if no_buy:
        for item, bt in no_buy[:8]:
            code = str(item.get("code") or "")
            lines.append(f"{code} {item.get('name') or code}：保留到轮动回测池。今天不买的原因是 {short_reason(item, bt)}。后续继续记录次日表现，用来校正追高过滤线和回踩确认线。")
    else:
        lines.append("今天没有新的 no-trade 样本需要追加。")

    lines.extend(["", "## 学习结论"])
    lines.append("结论一：报告必须先回答买不买、为什么不买、明天怎么用，不再把结论藏在表格里。")
    lines.append("结论二：强势观察池要变成可复盘的回踩买点；不是涨得强就买，而是看样本、位置、承接和止损。")
    lines.append("结论三：黄金、恒生、科创这些已有仓位先按持仓处理；只有趋势修复和回测同时支持，才从处理卡变成加仓卡。")

    lines.extend(["", "## 因子录入与判断"])
    lines.extend(factor_intake_lines())

    lines.extend(["", "## 来源优先级"])
    for item in rows[:8]:
        source = item["source"]
        meta = item["meta"]
        name = source.get("name", "-")
        evidence = []
        if item["hits"]:
            evidence.append("关键词 " + "、".join(item["hits"]))
        if meta.get("stars"):
            evidence.append(f"stars {meta.get('stars')}")
        lines.append(
            f"{name}：优先级 {item['score']}。用途是 {decision_support_for(source, item['hits'])}"
            f"证据：{'；'.join(evidence) if evidence else '本地资料源'}。下一步：{item['next_action']}"
        )

    lines.extend(["", "## 落地闸门"])
    lines.append("没有 clean radar 和回测同时支持的新票，不给明日买点。")
    lines.append("强势观察只做回踩确认，不做追高模板。")
    lines.append("学习源只服务于提高数据质量、回测纪律和动作卡表达，不直接变成买卖信号。")
    return "\n\n".join(lines) + "\n"


def build_report(payload: dict[str, Any], no_network: bool = False) -> str:
    keywords = payload.get("keywords", [])
    rows = []
    for source in payload.get("sources", []):
        meta: dict[str, Any] = {}
        error = ""
        if source.get("type") == "github" and not no_network:
            try:
                meta = fetch_github_meta(source.get("url", ""))
            except Exception as exc:
                error = concise_error(exc)
        score, hits = score_source(source, keywords, meta)
        rows.append(
            {
                "source": source,
                "meta": meta,
                "error": error,
                "score": score,
                "hits": hits,
                "next_action": next_action_for(source, score, hits),
            }
        )
    rows.sort(key=lambda item: item["score"], reverse=True)

    clean_radar = load_json(latest_ifind_clean_radar_path())
    backtest = load_json(latest_backtest_path())
    radar_items = clean_radar.get("items") or []
    holdings = [item for item in radar_items if as_float(item.get("shares"), 0) > 0]
    strong_watch = [item for item in radar_items if classify_strong_watch(item)]
    bt_by_code = {str(item.get("code")): item for item in (backtest.get("summaries") or [])}
    buy_candidates = []
    no_buy = []
    for item in strong_watch:
        code = str(item.get("code") or "")
        bt = bt_by_code.get(code) or {}
        sim = bt.get("similar_backtest") or {}
        win1 = as_float(sim.get("next1_win_rate"))
        med2 = as_float(sim.get("next2_median"))
        sample = int(as_float(sim.get("sample"), 0))
        change = as_float(item.get("change"))
        ret20 = as_float(item.get("ret20"))
        dist_ma20 = as_float(item.get("dist_ma20"))
        if sample >= 8 and win1 >= 0.55 and med2 > 0 and change < 5 and ret20 < 20 and dist_ma20 < 8:
            buy_candidates.append((item, bt))
        else:
            no_buy.append((item, bt))
    covered_count = sum(1 for item in strong_watch if str(item.get("code") or "") in bt_by_code)

    return build_plain_report(payload, rows, holdings, strong_watch, buy_candidates, no_buy, covered_count, bt_by_code)


def send_report_email(report: str) -> bool:
    load_local_env()
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")
    if not sender or not password or not recipient:
        print("email_skipped=missing SENDER_EMAIL/SENDER_PASSWORD/RECIPIENT_EMAIL")
        return False
    placeholders = ("your_", "example", "xxx", "fill", "replace")
    if any(token in sender.lower() for token in placeholders) or any(token in recipient.lower() for token in placeholders):
        print("email_skipped=placeholder email config")
        return False
    if any(token in password.lower() for token in placeholders):
        print("email_skipped=placeholder email password")
        return False

    html_report = "<pre style='font-size:14px;line-height:1.6;white-space:pre-wrap'>" + html.escape(report) + "</pre>"
    notifier = EmailNotifier(
        sender_email=sender,
        sender_password=password,
        smtp_server=os.getenv("SMTP_SERVER", "smtp.qq.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
    )
    ok = notifier.send_html_alert(recipient, "Learning Intake Report - quant radar", html_report)
    print(f"email_sent={ok}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a daily learning-intake report")
    parser.add_argument("--sources", default="examples/learning_sources.json")
    parser.add_argument("--output", default=str(LEARNING_REPORT))
    parser.add_argument("--no-network", action="store_true", help="Skip GitHub metadata fetch")
    parser.add_argument("--email", action="store_true", help="Send the generated report by email")
    args = parser.parse_args()

    sources = Path(args.sources)
    output = Path(args.output)
    report = build_report(load_sources(sources), no_network=args.no_network)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8-sig")
    print(f"learning_intake_report={output}")
    if args.email:
        ok = send_report_email(report)
        raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
