from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def llm_enabled() -> bool:
    return os.getenv("WAREHOUSE_AGENT_USE_LLM", "").lower() in {"1", "true", "yes", "on"}


def llm_config_status() -> dict[str, Any]:
    return {
        "enabled": llm_enabled(),
        "has_api_key": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    }


def llm_error_diagnostics(exc: Exception) -> dict[str, str]:
    return {
        "error_type": type(exc).__name__,
        "error_message": _redact_secret(str(exc))[:500],
    }


def get_chat_model():
    if not llm_enabled() or not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    kwargs = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "temperature": 0.1,
        "default_headers": {
            "User-Agent": os.getenv(
                "WAREHOUSE_AGENT_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36",
            )
        },
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _redact_secret(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", text)
    return re.sub(r"(?i)(api[_-]?key=)[^&\s]+", r"\1***", text)
