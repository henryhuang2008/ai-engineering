"""Qwen text-embedding-v4, with the query/document split lesson 6 asks for.

DeepSeek has no embeddings endpoint. That is not a problem: generation and
embedding are independent, and this file is the only place that knows the
embedder is Qwen.

Two details are easy to miss and expensive to get wrong:
  * the same model must be used at index time and query time;
  * the API embeds at most 10 texts per request, so batching is explicit.
"""

from __future__ import annotations

import os
from typing import Literal

import dashscope

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
        except Exception as exc:  # network, auth, quota - show the reason
            raise SystemExit(f"Qwen embedding request failed: {exc}") from exc
        items = sorted(response.embeddings, key=lambda item: item.index)
        vectors.extend(item.embedding for item in items)
    if len(vectors) != len(texts):
        raise SystemExit(
            f"expected {len(texts)} vectors from Qwen, received {len(vectors)}"
        )
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Index-time embedding: text_type='document'."""
    return _embed(texts, "document")


def embed_query(text: str) -> list[float]:
    """Query-time embedding: text_type='query', same model, same dimension."""
    return _embed([text], "query")[0]
