import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, status
from openai import OpenAI

from app.core.config import settings


@dataclass
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    input_tokens: int
    latency_ms: float
    cost_usd: float


@lru_cache
def _client() -> OpenAI:
    # API Key 누락은 호출 전에 명확한 서버 설정 오류로 처리한다.
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured in backend .env",
        )
    return OpenAI(api_key=settings.openai_api_key)


def chat(system_prompt: str, user_prompt: str) -> ChatResult:
    started = time.perf_counter()
    try:
        response = _client().chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"OpenAI chat request failed: {exc}") from exc

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    return ChatResult(
        text=response.choices[0].message.content or "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=(time.perf_counter() - started) * 1000,
        cost_usd=(
            input_tokens * settings.chat_input_cost_per_1m
            + output_tokens * settings.chat_output_cost_per_1m
        )
        / 1_000_000,
    )


def embed(texts: list[str], batch_size: int = 100) -> EmbeddingResult:
    started = time.perf_counter()
    vectors: list[list[float]] = []
    tokens = 0
    try:
        for i in range(0, len(texts), batch_size):
            response = _client().embeddings.create(
                model=settings.openai_embedding_model,
                input=texts[i : i + batch_size],
            )
            vectors.extend(item.embedding for item in response.data)
            tokens += response.usage.prompt_tokens
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"OpenAI embedding request failed: {exc}") from exc

    return EmbeddingResult(
        vectors=vectors,
        input_tokens=tokens,
        latency_ms=(time.perf_counter() - started) * 1000,
        cost_usd=tokens * settings.embedding_cost_per_1m / 1_000_000,
    )
