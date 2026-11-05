"""Shared configuration, LlamaIndex wiring, and a loud Ollama preflight.

Everything here is local: no API key, no cloud call. If Ollama is not running
or a model is missing, the scripts stop with the exact commands to fix it.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

load_dotenv()

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CHAT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
# Models advertise huge context windows (qwen3:4b-instruct says 262144).
# Asking Ollama for all of it allocates a KV cache of tens of GB and can kill
# llama-server with an out-of-memory error. 4096 is plenty for six reviews.
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "reviews.csv"
DB_DIR = ROOT / "chroma_db"
COLLECTION = "nimbus_reviews"


def not_reachable_message(error: object | None = None) -> str:
    detail = f"\n  detail: {error}" if error else ""
    return (
        f"Ollama is not reachable at {BASE_URL}.{detail}\n"
        "  1. Install (Windows):  winget install Ollama.Ollama\n"
        "     or download:        https://ollama.com/download\n"
        "  2. Start the server:   ollama serve\n"
        "  3. Pull the models:    ollama pull qwen3:4b-instruct\n"
        "                         ollama pull nomic-embed-text\n"
        "  Then run this script again."
    )


def pull_message(models: list[str]) -> str:
    lines = "\n".join(f"  ollama pull {model}" for model in models)
    return (
        f"Ollama is running, but these models are missing:\n{lines}\n"
        "Pull them once; they stay in the local model store."
    )


def _matches(model: str, installed: list[str]) -> bool:
    if ":" in model:
        return model in installed
    return any(name == model or name.startswith(f"{model}:") for name in installed)


def installed_models() -> list[str]:
    """Model names from Ollama, or a RuntimeError with install instructions."""
    try:
        response = requests.get(f"{BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise RuntimeError(not_reachable_message(error)) from error

    return [item.get("name", "") for item in payload.get("models", [])]


def require_models(*, need_chat: bool = True) -> list[str]:
    """Check the models this script needs; ingest only needs embeddings."""
    models = installed_models()
    required = [EMBED_MODEL] + ([CHAT_MODEL] if need_chat else [])
    missing = [model for model in required if not _matches(model, models)]
    if missing:
        raise RuntimeError(pull_message(missing))
    return models


def configure(*, need_llm: bool = True) -> None:
    """Set LlamaIndex's process-wide model handles."""
    Settings.embed_model = OllamaEmbedding(
        model_name=EMBED_MODEL,
        base_url=BASE_URL,
    )
    if need_llm:
        Settings.llm = Ollama(
            model=CHAT_MODEL,
            base_url=BASE_URL,
            request_timeout=120,
            temperature=0,
            context_window=NUM_CTX,
        )
