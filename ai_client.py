"""Small OpenAI-compatible AI client for Qwen, Kimi, and custom providers."""

import html
import json
import logging
import os
from typing import Any, Dict, Optional

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
}


def _env_enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _provider_config() -> Dict[str, str]:
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


def ai_is_configured() -> bool:
    """Return True when AI summary generation should run."""
    return _env_enabled("AI_ENABLED") and bool(_provider_config()["api_key"])


def chat_completion(prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """Call an OpenAI-compatible chat completion endpoint."""
    config = _provider_config()
    if not config["api_key"]:
        logger.info("AI summary skipped: missing API key")
        return None

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": float(os.getenv("AI_TEMPERATURE", "0.2")),
        "max_tokens": int(os.getenv("AI_MAX_TOKENS", "500")),
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
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("AI summary failed and will be skipped: %s", exc)
        return None


def build_rate_prompt(result: Dict[str, Any]) -> str:
    """Build a compact prompt from the monitor result."""
    return f"""
Please summarize this bank-rate monitor result in Chinese.
Keep it short, practical, and conservative. Do not invent data.

Data:
{json.dumps(result, ensure_ascii=False, indent=2, default=str)}

Required output:
1. One-sentence status
2. Whether action is worth considering
3. Main risk or missing data
""".strip()


def generate_ai_summary_html(result: Dict[str, Any]) -> str:
    """Return an optional HTML block with AI advice."""
    if not ai_is_configured():
        return ""

    summary = chat_completion(
        build_rate_prompt(result),
        system_prompt=(
            "You are a cautious personal finance assistant. "
            "You provide operational summaries, not investment guarantees."
        ),
    )
    if not summary:
        return ""

    return f"""
    <div style="margin-top: 20px; padding: 15px; background-color: #f6f8fa; border-left: 4px solid #6f42c1; border-radius: 4px;">
        <p style="margin: 0 0 8px 0; font-size: 16px; font-weight: bold; color: #24292f;">AI 简报</p>
        <div style="white-space: pre-wrap; font-size: 14px; color: #24292f;">{html.escape(summary)}</div>
    </div>
    """
