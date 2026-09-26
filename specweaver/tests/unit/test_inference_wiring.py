"""Provider wiring + OpenAI-compatible adapter translation tests."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from specweaver.adapters.driven.inference import (
    DeterministicEmbedding,
    MiniMaxEmbedding,
    NullLLM,
    OpenAIChatLLM,
    OpenAIEmbedding,
)
from specweaver.shared.config import InferenceSettings, Settings
from specweaver.shared.di import build_inference
from specweaver.shared.errors import (
    BackendConnectionError,
    SWError,
)


def _inference(provider: str, key: str | None = None) -> Settings:
    settings = Settings(_env_file=None)
    settings.inference = InferenceSettings(
        provider=provider,
        api_key=SecretStr(key) if key else None,
        base_url="http://infer",
        model="m",
        embed_model="e",
        dim=8,
    )
    return settings


def test_provider_selection_matrix() -> None:
    stack = build_inference(_inference("none"))
    assert isinstance(stack.llm, NullLLM)
    assert isinstance(stack.embedding, DeterministicEmbedding)

    stack = build_inference(_inference("deepseek", "sk-x"))
    assert isinstance(stack.llm, OpenAIChatLLM)
    # deepseek has no embeddings endpoint: vectors stay deterministic
    assert isinstance(stack.embedding, DeterministicEmbedding)

    stack = build_inference(_inference("minimax", "sk-x"))
    assert isinstance(stack.embedding, MiniMaxEmbedding)

    stack = build_inference(_inference("qianwen", "sk-x"))
    assert isinstance(stack.embedding, OpenAIEmbedding)

    stack = build_inference(_inference("qianwen"))
    assert isinstance(stack.llm, NullLLM)
    assert stack.warning and "qianwen" in stack.warning


def _llm(handler) -> OpenAIChatLLM:
    settings = _inference("deepseek", "sk-x").inference
    return OpenAIChatLLM(
        settings, transport=httpx.MockTransport(handler)
    )


async def test_chat_parses_content_usage_and_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"objective":"o","keywords":["k"]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5},
            },
        )

    result = await _llm(handler).complete(
        "task", schema={"type": "object"}
    )
    assert result.structured == {"objective": "o", "keywords": ["k"]}
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 5


async def test_chat_error_translation() -> None:
    with pytest.raises(SWError):
        await _llm(
            lambda r: httpx.Response(401, text="bad key")
        ).complete("t")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(BackendConnectionError):
        await _llm(boom).complete("t")


async def test_openai_embeddings_shape_dim_and_errors() -> None:
    settings = _inference("qianwen", "sk-x").inference

    def ok(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert sent["dimensions"] == 8  # dim must be requested explicitly
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1] * 8} for _ in sent["input"]
                ]
            },
        )

    emb = OpenAIEmbedding(settings, transport=httpx.MockTransport(ok))
    vectors = await emb.embed(["x"])
    assert len(vectors[0]) == 8


async def test_openai_embeddings_chunks_large_batches() -> None:
    """Provider caps batch at 10: 25 inputs must become 10+10+5 calls."""
    settings = _inference("qianwen", "sk-x").inference
    seen: list[int] = []

    def ok(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert len(sent["input"]) <= 10
        seen.append(len(sent["input"]))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [float(i)] * 8}
                    for i in range(len(sent["input"]))
                ]
            },
        )

    emb = OpenAIEmbedding(settings, transport=httpx.MockTransport(ok))
    texts = [f"t{i}" for i in range(25)]
    vectors = await emb.embed(texts)
    assert seen == [10, 10, 5]
    assert len(vectors) == 25
    assert vectors[10][0] == 0.0  # order preserved across batches

    def wrong_dim(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}]})

    emb = OpenAIEmbedding(
        settings, transport=httpx.MockTransport(wrong_dim)
    )
    with pytest.raises(SWError):
        await emb.embed(["x"])

    emb = OpenAIEmbedding(
        settings,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(401, text="nope")
        ),
    )
    with pytest.raises(SWError):
        await emb.embed(["x"])
