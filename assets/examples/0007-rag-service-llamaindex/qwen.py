"""Qwen text-embedding-v4 for LlamaIndex, keeping the query/document split."""

from __future__ import annotations

import os
from typing import Any, Literal

import dashscope
from llama_index.core.embeddings import BaseEmbedding

from common import (
    DEFAULT_BASE_URL,
    EMBED_BATCH,
    EMBED_DIM,
    EMBED_MODEL,
    MissingKey,
    missing_keys_message,
)

TextType = Literal["document", "query"]


def _client() -> dashscope.Client:
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise MissingKey(missing_keys_message(["DASHSCOPE_API_KEY"]))
    base_url = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL)
    return dashscope.Client(api_key=key, base_url=base_url)


def _embed(texts: list[str], text_type: TextType) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        try:
            response = client.embeddings.create(
                model=EMBED_MODEL,
                input=batch,
                dimension=EMBED_DIM,
                text_type=text_type,
                output_type="dense",
            )
        except Exception as exc:
            raise SystemExit(f"Qwen embedding request failed: {exc}") from exc
        items = sorted(response.embeddings, key=lambda item: item.index)
        vectors.extend(item.embedding for item in items)
    if len(vectors) != len(texts):
        raise SystemExit(
            f"expected {len(texts)} vectors from Qwen, received {len(vectors)}"
        )
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "document")


def embed_query(text: str) -> list[float]:
    return _embed([text], "query")[0]


class QwenEmbedding(BaseEmbedding):
    """LlamaIndex adapter: batch documents, asymmetric query embedding."""

    model_name: str = EMBED_MODEL

    def _get_query_embedding(self, query: str) -> list[float]:
        return embed_query(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return embed_query(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return embed_documents([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return embed_documents(texts)

    def _get_text_embedding_batch(
        self, texts: list[str], **kwargs: Any
    ) -> list[list[float]]:
        return embed_documents(texts)
