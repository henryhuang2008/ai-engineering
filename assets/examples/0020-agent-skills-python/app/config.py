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
    library: Path
    require_loaded: bool

    def require_llm(self) -> tuple[str, str, str]:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY (or DEEPSEEK_API_KEY) is required for `ask`. "
                "The model is any OpenAI-compatible chat endpoint; DeepSeek is the "
                "course default."
            )
        return self.api_key, self.base_url, self.model


def get_settings() -> Settings:
    library = Path(os.getenv("SKILLS_DIR", "skills"))
    if not library.is_absolute():
        library = (PROJECT_ROOT / library).resolve()
    return Settings(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or None,
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        library=library,
        require_loaded=os.getenv("REQUIRE_LOADED", "1") not in {"0", "false", "False"},
    )
