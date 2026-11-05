import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

import app.retrieval.embeddings as embeddings


def test_validate_embedding_response_checks_count_dimensions_and_finite_values() -> None:
    response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])

    assert embeddings.validate_embedding_response(response, 3) == [0.1, 0.2, 0.3]
    with pytest.raises(ValueError, match="exactly one"):
        embeddings.validate_embedding_response(SimpleNamespace(data=[]), 3)
    with pytest.raises(ValueError, match="exactly 3"):
        embeddings.validate_embedding_response(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])]),
            3,
        )
    with pytest.raises(ValueError, match="finite"):
        embeddings.validate_embedding_response(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, float("nan"), 0.3])]),
            3,
        )
    with pytest.raises(ValueError, match="finite numbers"):
        embeddings.validate_embedding_response(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, "0.2", 0.3])]),
            3,
        )


def test_qwen_embedder_uses_configured_model_dimensions_and_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeEmbeddings:
        async def create(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)
            self.embeddings = FakeEmbeddings()

        async def close(self) -> None:
            calls.append({"closed": True})

    monkeypatch.setattr(embeddings, "AsyncOpenAI", FakeClient)
    config = SimpleNamespace(
        dashscope_api_key=SecretStr("test-key"),
        qwen_base_url="https://dashscope.example/v1",
        qwen_embedding_model="text-embedding-test",
        qwen_embedding_dimensions=2,
    )

    embedder = embeddings.QwenQueryEmbedder(config)
    vector = asyncio.run(embedder.embed_query("  annual revenue  "))
    asyncio.run(embedder.aclose())

    assert vector == [0.1, 0.2]
    assert calls == [
        {
            "api_key": "test-key",
            "base_url": "https://dashscope.example/v1",
            "timeout": 30.0,
            "max_retries": 2,
        },
        {
            "model": "text-embedding-test",
            "input": "  annual revenue  ",
            "dimensions": 2,
            "encoding_format": "float",
        },
        {"closed": True},
    ]


def test_qwen_embedder_requires_credentials_and_endpoint() -> None:
    config = SimpleNamespace(
        dashscope_api_key=None,
        qwen_base_url="https://dashscope.example/v1",
        qwen_embedding_model="text-embedding-test",
        qwen_embedding_dimensions=2,
    )

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY and QWEN_BASE_URL"):
        embeddings.QwenQueryEmbedder(config)
