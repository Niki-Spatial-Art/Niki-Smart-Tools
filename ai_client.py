"""Optional OpenAI-compatible AI summary client."""

import json
import logging
import os
from typing import Dict, Optional

import requests


logger = logging.getLogger(__name__)

PROVIDERS = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "key_env": "DASHSCOPE_API_KEY",
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "key_env": "KIMI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
}


def env_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def provider_config() -> Dict[str, str]:
    provider = os.getenv("AI_PROVIDER", "qwen").strip().lower()
    config = dict(PROVIDERS.get(provider, PROVIDERS["qwen"]))
    config["provider"] = provider
    config["base_url"] = os.getenv("AI_BASE_URL", config["base_url"]).rstrip("/")
    config["model"] = os.getenv("AI_MODEL", config["model"])
    key_env = os.getenv("AI_KEY_ENV", config["key_env"])
    config["api_key"] = (
        os.getenv("AI_API_KEY")
        or os.getenv(key_env)
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    return config


def chat_completion(prompt: str, system_prompt: str) -> Optional[str]:
    config = provider_config()
    if not env_enabled("AI_ENABLED") or not config["api_key"]:
        logger.info("AI summary skipped")
        return None

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(os.getenv("AI_TEMPERATURE", "0.2")),
        "max_tokens": int(os.getenv("AI_MAX_TOKENS", "700")),
    }

    try:
        response = requests.post(
            f"{config['base_url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=int(os.getenv("AI_TIMEOUT_SECONDS", "30")),
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("AI summary failed and will be skipped: %s", exc)
        return None


def generate_ai_summary(report: Dict) -> str:
    compact = []
    for item in report.get("results", []):
        compact.append(
            {
                "code": item["code"],
                "name": item["name"],
                "price": item["price"],
                "pct_change": item["pct_change"],
                "ma20": item["ma20"],
                "ma60": item["ma60"],
                "level": item["level"],
                "action": item["action"],
                "reasons": item["reasons"][:3],
                "strategy": item.get("strategy", {}),
            }
        )

    stock_compact = []
    for item in report.get("stock_radar", {}).get("results", [])[:18]:
        stock_compact.append(
            {
                "code": item["code"],
                "name": item["name"],
                "layer": item.get("layer_name"),
                "price": item["price"],
                "pct_change": item["pct_change"],
                "ma20": item["ma20"],
                "ma60": item["ma60"],
                "level": item["level"],
                "action": item["action"],
                "reasons": item["reasons"][:3],
            }
        )

    portfolio = report.get("portfolio", {})
    pilot = (portfolio.get("capital_plan") or {}).get("short_term_pilot") or {}
    short_term_policy = {
        "enabled": pilot.get("enabled"),
        "stage": pilot.get("stage"),
        "capital_per_stock": pilot.get("capital_per_stock"),
        "strong_signal_capital_per_stock": pilot.get("strong_signal_capital_per_stock"),
        "max_stocks": pilot.get("max_stocks"),
        "max_total_capital": pilot.get("max_total_capital"),
        "daily_profit_target": pilot.get("daily_profit_target"),
        "daily_loss_soft_stop": pilot.get("daily_loss_soft_stop"),
        "daily_loss_hard_stop": pilot.get("daily_loss_hard_stop"),
        "no_chase_pct": pilot.get("no_chase_pct"),
    }

    prompt = f"""
请基于下面 ETF 雷达和 AI 产业链个股雷达结果，给出中文策略简报。

要求：
1. 不要承诺收益，不要说一定会涨。
2. 用贝叶斯口径表达：先验是什么，新证据改变了什么，后验行动是什么。
3. 强调纪律：绿色可小仓研究，黄色观察，红色禁止追买。
4. 特别提醒高溢价/停牌风险样本不要追。
5. 加一条反身性检查：上涨是否正在制造追涨叙事，拥挤是否比基本面证据更强。
6. 如果 strategy 里出现 BUY / SELL / BLOCK，请优先说明执行动作和金额。
7. 输出控制在 6 条以内，每条短句。
8. 不要引用书名，不要讲理论，只把理论转成交易纪律。
9. 必须提醒今天最容易犯的一个心理错误，例如追涨、锚定成本、亏损后急于扳回、错过后的补偿性买入。
10. 如果强势标的是 QDII、高溢价、风险公告或当前仓位过高，要把叙事热度降权。
11. 对趋势仓检查入场规则、头寸规模、止损线和退出条件；不要因为单日突破或强势叙事临时扩大仓位。
12. 个股部分只做卫星仓候选发现，重点寻找存算一体、存储、光模块、AI芯片、AI服务器中“层级共振 + 龙头确认 + 量价突破”的线索。
13. 如果只有单只个股强、同层级不强，要提示这可能只是情绪或个股事件，不是主线确认。
14. 短线仓位规则必须以“当前短线仓位规则”为准，不得沿用旧的1万元/2万元/最多3只/6万元口径；如果规则显示2万元/3万元/最多4只/10万元，就必须按新口径表达。
15. “日目标”只作为测算和复盘压力测试，不允许写成保证收益，也不允许为了凑目标建议追高或补仓。

当前短线仓位规则：
{json.dumps(short_term_policy, ensure_ascii=False, indent=2)}

账户：
{json.dumps(portfolio, ensure_ascii=False, indent=2)}

ETF 数据：
{json.dumps(compact, ensure_ascii=False, indent=2)}

AI 产业链个股数据：
{json.dumps(stock_compact, ensure_ascii=False, indent=2)}
""".strip()

    return chat_completion(
        prompt,
        (
            "你是一个谨慎的 ETF 与 AI 产业链交易纪律助手，只做风险提示和执行纪律总结。"
            "你的方法是把行情当证据，而不是预言；区分先验、新证据和后验行动；"
            "同时检查市场反身性、叙事过热、仓位拥挤、趋势仓执行纪律和个股卫星仓风险。"
        ),
    ) or ""
