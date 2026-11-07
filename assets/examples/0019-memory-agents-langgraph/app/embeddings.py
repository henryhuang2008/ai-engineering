"""A minimal LangChain Embeddings adapter for OpenAI-compatible providers.

Written with the OpenAI SDK directly so the request carries raw strings.
LangChain's OpenAIEmbeddings defaults to tokenising locally with tiktoken,
which some compatible endpoints (including DashScope) reject.
"""

from __future__ import annotations

import math

from langchain_core.embeddings import Embeddings
from openai import OpenAI

from app.config import Settings


class OpenAICompatibleEmbeddings(Embeddings):
    def __init__(self, settings: Settings) -> None:
        if not settings.embed_api_key or not settings.embed_base_url or not settings.embed_model:
            raise ValueError("EMBED_API_KEY, EMBED_BASE_URL and EMBED_MODEL are required")
        self._model = settings.embed_model
        self._dimensions = settings.embed_dims
        self._client = OpenAI(
            api_key=settings.embed_api_key,
            base_url=settings.embed_base_url,
            timeout=30.0,
            max_retries=2,
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
            encoding_format="float",
        )
        vectors = []
        for item in response.data:
            vector = list(item.embedding)
            if len(vector) != self._dimensions:
                raise ValueError(
                    f"Embedding has {len(vector)} dimensions, expected {self._dimensions}"
                )
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("Embedding contains a non-finite value")
            vectors.append(vector)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
