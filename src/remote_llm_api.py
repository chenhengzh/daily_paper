"""集中管理 LLM API 调用：重试 / 限流(QPM) / 并发。

本文件主要服务于评测与离线数据合成（例如用远程大模型生成 memory-updater 轨迹）。

支持两种客户端模式（通过环境变量 OPENAI_API_TYPE 切换）：
  - "openai"（默认）：使用 AsyncOpenAI，适配标准 OpenAI-compatible 网关
  - "azure"：使用 AsyncAzureOpenAI，适配 Azure OpenAI 服务
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import APIError, APITimeoutError, RateLimitError, AsyncAzureOpenAI, AsyncOpenAI


def _is_likely_limit_error(e: Exception) -> bool:
    s = str(e)
    return (
        "qpm limit" in s
        or "reach token limit" in s
        or "-2001" in s
        or "-2004" in s
        or "RateLimit" in s
        or "429" in s
    )


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "":
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)


@dataclass(frozen=True)
class RemoteLLMConfig:
    # API 类型："openai"（默认，标准兼容网关）或 "azure"
    API_TYPE: str = os.getenv("OPENAI_API_TYPE", "openai")

    # OpenAI-compatible 网关地址（OPENAI_API_TYPE=openai 时使用）
    OPENAI_BASE_URL: str = os.getenv(
        "OPENAI_BASE_URL", "https://aigc.sankuai.com/v1/openai/native"
    )

    # Azure 网关地址（OPENAI_API_TYPE=azure 时使用）
    AZURE_ENDPOINT: str = os.getenv(
        "AZURE_ENDPOINT", "https://search.bytedance.net/gpt/openapi/online/v2/crawl"
    )
    API_VERSION: str = os.getenv("AZURE_API_VERSION", "2024-03-01-preview")

    # IMPORTANT: 不要在代码里硬编码 Key。请通过环境变量注入。
    AZURE_API_KEY: str = os.getenv("AZURE_API_KEY", os.getenv("OPENAI_API_KEY", ""))

    MODEL_NAME: str = os.getenv("AZURE_MODEL_NAME", os.getenv("OPENAI_MODEL_NAME", "deepseek-v3.2-huawei"))

    # --- 核心超参 ---
    # QPM 要求：Gemini 2.5 设置为 256（可通过 env 覆盖）
    QPM: int = _env_int("AZURE_QPM", 256)
    # 并发上限：避免同时大量 in-flight request
    MAX_CONCURRENCY: int = _env_int("AZURE_MAX_CONCURRENCY", 64)
    # 网络/SDK timeout（秒）。同时会用 asyncio.wait_for 兜底。
    TIMEOUT_S: float = _env_float("AZURE_TIMEOUT_S", 120.0)
    # 重试与退避
    API_RETRIES: int = _env_int("AZURE_API_RETRIES", 6)
    BACKOFF_INITIAL_S: float = _env_float("AZURE_BACKOFF_INITIAL_S", 1.0)
    BACKOFF_MAX_S: float = _env_float("AZURE_BACKOFF_MAX_S", 120.0)


class AsyncQpmRateLimiter:
    """一个简单的 QPM 限流器：通过强制最小间隔实现。

    - 对外只暴露 `wait()`
    - 支持并发调用（内部用 lock 串行分配时间片）
    """

    def __init__(self, qpm: int):
        qpm = int(qpm)
        if qpm <= 0:
            raise ValueError(f"qpm must be positive, got {qpm}")
        self._min_interval_s = 60.0 / float(qpm)
        self._lock = asyncio.Lock()
        self._next_allowed_ts = 0.0

    async def wait(self) -> None:
        delay = 0.0
        async with self._lock:
            now = time.monotonic()
            if self._next_allowed_ts <= 0.0:
                self._next_allowed_ts = now
            delay = max(0.0, self._next_allowed_ts - now)
            self._next_allowed_ts = max(self._next_allowed_ts, now) + self._min_interval_s
        if delay > 0:
            await asyncio.sleep(delay)


def _supports_reasoning_effort(model: str) -> bool:
    m = (model or "").lower()
    # Gemini 2.5 以及大多数 OpenAI-compatible 网关不一定接受 reasoning_effort 参数。
    if m.startswith("gemini"):
        return False
    # 仅对明确的 reasoning 系列保守开启；其他情况不传。
    return m.startswith("o1") or m.startswith("o3")


def build_default_client(config: RemoteLLMConfig) -> AsyncOpenAI | AsyncAzureOpenAI:
    if not config.AZURE_API_KEY:
        raise RuntimeError(
            "Missing API key: set `OPENAI_API_KEY` (or `AZURE_API_KEY`) for remote LLM calls."
        )
    if config.API_TYPE == "azure":
        return AsyncAzureOpenAI(
            azure_endpoint=config.AZURE_ENDPOINT,
            api_key=config.AZURE_API_KEY,
            api_version=config.API_VERSION,
        )
    else:
        # 标准 OpenAI-compatible 网关
        return AsyncOpenAI(
            base_url=config.OPENAI_BASE_URL,
            api_key=config.AZURE_API_KEY,
        )


_DEFAULT_CONFIG = RemoteLLMConfig()
_DEFAULT_RATE_LIMITER = AsyncQpmRateLimiter(_DEFAULT_CONFIG.QPM)
_DEFAULT_SEMAPHORE = asyncio.Semaphore(_DEFAULT_CONFIG.MAX_CONCURRENCY)
_DEFAULT_CLIENT: AsyncOpenAI | AsyncAzureOpenAI | None = None


def get_default_client() -> AsyncOpenAI | AsyncAzureOpenAI:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = build_default_client(_DEFAULT_CONFIG)
    return _DEFAULT_CLIENT


async def chat_completion_text(
    *,
    namespace: str,
    client,
    rate_limiter,
    llm_semaphore: asyncio.Semaphore,
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    reasoning_effort: Optional[str] = None,
    request_kwargs: Optional[Dict[str, Any]] = None,
    api_retries: Optional[int] = None,
) -> str:

    last_err: Optional[Exception] = None
    max_retries = int(api_retries) if api_retries is not None else int(_DEFAULT_CONFIG.API_RETRIES)
    max_retries = max(1, max_retries)
    backoff_time = float(_DEFAULT_CONFIG.BACKOFF_INITIAL_S)
    for attempt in range(max_retries):
        try:
            await rate_limiter.wait()
            async with llm_semaphore:
                kwargs = dict(request_kwargs or {})

                # per-request timeout：避免 SDK/网络问题导致单次请求无限期卡住
                timeout_s = float(kwargs.pop("timeout_s", 0.0) or 0.0)
                if timeout_s <= 0:
                    timeout_s = float(_DEFAULT_CONFIG.TIMEOUT_S)

                # OpenAI Python SDK 支持 per-request timeout 参数（秒）
                # 但不同网关实现可能不一致，因此仍用 asyncio.wait_for 兜底。
                if timeout_s and timeout_s > 0:
                    kwargs.setdefault("timeout", timeout_s)


                create_kwargs: dict[str, Any] = dict(
                    model=model,
                    messages=messages,
                    stream=False,
                    max_tokens=int(max_tokens),
                    temperature=float(temperature),
                )
                if reasoning_effort and _supports_reasoning_effort(model):
                    create_kwargs["reasoning_effort"] = reasoning_effort

                call = client.chat.completions.create(
                    **create_kwargs,
                    **kwargs,
                )

                # 双保险：即便 SDK 的 timeout 未生效，也用 asyncio.wait_for 强制打断。
                if timeout_s and timeout_s > 0:
                    resp = await asyncio.wait_for(call, timeout=timeout_s)
                else:
                    resp = await call

            content = resp.choices[0].message.content
            return str(content)

        except (APIError, RateLimitError, APITimeoutError) as e:
            last_err = e
        except Exception as e:
            last_err = e

        if attempt < max_retries - 1:
            sleep_s = float(backoff_time)
            if last_err is not None and _is_likely_limit_error(last_err):
                sleep_s = max(sleep_s, 15.0)
            sleep_s += random.uniform(0.0, 2.0)
            await asyncio.sleep(sleep_s)
            backoff_time = min(backoff_time * 2.0, float(_DEFAULT_CONFIG.BACKOFF_MAX_S))

    raise RuntimeError(f"LLM call failed after retries ns={namespace}: {last_err}")


async def default_chat_completion_text(
    *,
    namespace: str,
    messages: list,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    reasoning_effort: Optional[str] = None,
    request_kwargs: Optional[Dict[str, Any]] = None,
    api_retries: Optional[int] = None,
) -> str:
    """使用默认 client/限流器/并发控制的快捷封装。"""

    return await chat_completion_text(
        namespace=namespace,
        client=get_default_client(),
        rate_limiter=_DEFAULT_RATE_LIMITER,
        llm_semaphore=_DEFAULT_SEMAPHORE,
        model=str(model or _DEFAULT_CONFIG.MODEL_NAME),
        messages=messages,
        max_tokens=int(max_tokens),
        temperature=float(temperature),
        reasoning_effort=reasoning_effort,
        request_kwargs=request_kwargs,
        api_retries=api_retries,
    )


from typing import AsyncGenerator

async def default_chat_completion_stream(
    *,
    namespace: str,
    messages: list,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> AsyncGenerator[str, None]:
    """流式版本：逐 token yield 文本片段。"""
    await _DEFAULT_RATE_LIMITER.wait()
    client = get_default_client()
    async with _DEFAULT_SEMAPHORE:
        stream = await client.chat.completions.create(
            model=str(model or _DEFAULT_CONFIG.MODEL_NAME),
            messages=messages,
            stream=True,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            timeout=float(_DEFAULT_CONFIG.TIMEOUT_S),
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
