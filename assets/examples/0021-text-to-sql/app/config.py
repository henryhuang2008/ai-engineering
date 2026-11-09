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
    db_path: Path
    max_attempts: int

    def require_llm(self) -> tuple[str, str, str]:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for `ask` and `demo`. This example "
                "points ChatOpenAI at an OpenAI-compatible endpoint (DeepSeek by "
                "default)."
            )
        return self.api_key, self.base_url, self.model


def get_settings() -> Settings:
    db_path = Path(os.getenv("SQL_DB_PATH", "data/northstar.db"))
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()
    return Settings(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or None,
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        db_path=db_path,
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "3")),
    )
