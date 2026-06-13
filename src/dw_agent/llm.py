from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


def llm_enabled() -> bool:
    return os.getenv("WAREHOUSE_AGENT_USE_LLM", "").lower() in {"1", "true", "yes", "on"}


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
    }
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)
