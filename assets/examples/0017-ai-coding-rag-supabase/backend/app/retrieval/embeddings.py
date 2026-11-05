from __future__ import annotations

import math
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings, settings


class QueryEmbedder(Protocol):
    async def embed_query(self, query: str) -> list[float]: ...

    async def aclose(self) -> None: ...


class QwenQueryEmbedder:
    def __init__(self, config: Settings = settings) -> None:
        if not config.dashscope_api_key or not config.qwen_base_url:
            raise RuntimeError(
                "DASHSCOPE_API_KEY and QWEN_BASE_URL are required for query embeddings."
            )
        self._model = config.qwen_embedding_model
        self._dimensions = config.qwen_embedding_dimensions
        self._client = AsyncOpenAI(
            api_key=config.dashscope_api_key.get_secret_value(),
            base_url=config.qwen_base_url,
            timeout=30.0,
            max_retries=2,
        )

    async def embed_query(self, query: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=query,
            dimensions=self._dimensions,
            encoding_format="float",
        )
        return validate_embedding_response(response, self._dimensions)

    async def aclose(self) -> None:
        await self._client.close()


def validate_embedding_response(response: object, dimensions: int) -> list[float]:
    data = getattr(response, "data", None)
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("Embedding provider must return exactly one query vector.")

    embedding = getattr(data[0], "embedding", None)
    if not isinstance(embedding, list) or len(embedding) != dimensions:
        raise ValueError(f"Query embedding must contain exactly {dimensions} values.")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in embedding
    ):
        raise ValueError("Query embedding values must be finite numbers.")
    return [float(value) for value in embedding]
