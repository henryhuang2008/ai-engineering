from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import Settings


def build_llm(settings: Settings) -> ChatOpenAI:
    api_key, base_url, model = settings.require_llm()
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )
