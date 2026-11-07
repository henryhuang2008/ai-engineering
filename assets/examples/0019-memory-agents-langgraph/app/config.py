from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    model: str
    database_url: str | None
    embed_model: str | None
    embed_base_url: str | None
    embed_api_key: str | None
    embed_dims: int
    max_context_tokens: int
    keep_last_messages: int
    recall_limit: int

    def require_llm(self) -> tuple[str, str, str]:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. This example points ChatOpenAI at "
                "an OpenAI-compatible endpoint (DeepSeek by default)."
            )
        return self.api_key, self.base_url, self.model

    @property
    def semantic_memory(self) -> bool:
        return bool(self.embed_model and self.embed_api_key)


def get_settings() -> Settings:
    return Settings(
        api_key=os.getenv("OPENAI_API_KEY") or None,
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        database_url=os.getenv("DATABASE_URL") or None,
        embed_model=os.getenv("EMBED_MODEL") or None,
        embed_base_url=os.getenv("EMBED_BASE_URL") or None,
        embed_api_key=os.getenv("EMBED_API_KEY") or None,
        embed_dims=int(os.getenv("EMBED_DIMS", "1536")),
        max_context_tokens=int(os.getenv("MAX_CONTEXT_TOKENS", "2000")),
        keep_last_messages=int(os.getenv("KEEP_LAST_MESSAGES", "6")),
        recall_limit=int(os.getenv("RECALL_LIMIT", "5")),
    )
