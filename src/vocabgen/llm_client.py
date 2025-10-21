"""
LLM client wrapper supporting:
- Gemini (google-genai)
- OpenAI (official OpenAI Python SDK)
- Local Ollama (ollama package)
from llm_client import generate_text, set_logging_level

set_logging_level("INFO")
resp = generate_text(
    provider="gemini",
    model="gemini-2.5-pro",
    system_prompt="You are a helpful assistant.",
    user_prompt="Explain why the sky is blue in one paragraph.",
    model_params={"temperature": 0.2},
    max_retries=2,
    rate_limit_per_minute=30,
)
print(resp)
"""

from __future__ import annotations
import os
import time
import random
import logging
from collections import deque
from typing import Optional, Dict, Any

# Conditional imports
try:
    from google import genai  # type: ignore
except Exception:
    genai = None  # type: ignore

try:
    from openai import OpenAI  # official OpenAI python client
except Exception:
    OpenAI = None  # type: ignore

try:
    from ollama import Client as OllamaClient  # type: ignore
except Exception:
    OllamaClient = None  # type: ignore


# Logger for library
logger = logging.getLogger("llm_client")


class RateLimiter:
    """
    Simple sliding-window rate limiter: max_calls per minute.
    If max_calls is None or <= 0, no limiting is applied.
    """

    def __init__(self, max_calls_per_minute: Optional[int] = None):
        self.max_calls = int(max_calls_per_minute) if max_calls_per_minute else None
        # store timestamps (float seconds) of recent calls
        self._timestamps = deque()

    WINDOW_SECONDS: float = 60.0

    def _clear_old_timestamps(self):
        now = time.time()
        while self._timestamps and (now - self._timestamps[0]) > self.WINDOW_SECONDS:
            self._timestamps.popleft()

    def acquire(self) -> None:
        """Block until a request is allowed under the configured rate limit."""
        if not self.max_calls:
            return

        self._clear_old_timestamps()
        now = time.time()
        if len(self._timestamps) < self.max_calls:
            # Allow immediately
            self._timestamps.append(now)
            return

        # Need to wait until the oldest timestamp is older than window_seconds
        oldest = self._timestamps[0]
        sleep_for = (oldest + self.WINDOW_SECONDS) - now
        logger.debug("Rate limit reached: sleeping for %.3f seconds", sleep_for)
        if sleep_for > 0:
            time.sleep(sleep_for)

        # After sleeping, append new timestamp (and cleanup)
        self._clear_old_timestamps()
        now = time.time()
        self._timestamps.append(now)


def _extract_text_from_response(obj: Any) -> str:
    """
    Robust extractor for multiple SDK response shapes.
    Tries a series of common possibilities and returns the first found assistant text.
    """
    # If object has .text
    if obj is None:
        return ""
    if hasattr(obj, "text"):
        try:
            return str(obj.text)
        except Exception:
            pass

    # If OpenAI-like: response.choices[0].message.content or response.choices[0].message['content']
    try:
        choices = getattr(obj, "choices", None) or (obj.get("choices") if isinstance(obj, dict) else None)
        if choices and len(choices) > 0:
            first = choices[0]
            # new SDKs may provide message as attribute or dict
            message = getattr(first, "message", None) or first.get("message") if isinstance(first, dict) else None
            if message:
                # message.content
                content = getattr(message, "content", None) or (message.get("content") if isinstance(message, dict) else None)
                if content:
                    return str(content)
            # older shapes: first.text or first.delta or first["text"]
            if hasattr(first, "text"):
                return str(first.text)
            if isinstance(first, dict):
                # check 'message', 'text', 'delta'
                if "text" in first and first["text"]:
                    return str(first["text"])
                if "delta" in first:
                    delta = first["delta"]
                    if isinstance(delta, dict) and "content" in delta:
                        return str(delta["content"])
    except Exception:
        pass

    # If Ollama-like: maybe returns dict with 'choices'-> [{'content': '...'}] or {'content': '...'}
    try:
        if isinstance(obj, dict):
            # direct content
            if "content" in obj and obj["content"]:
                return str(obj["content"])
            if "result" in obj and isinstance(obj["result"], dict) and "content" in obj["result"]:
                return str(obj["result"]["content"])
            # choices
            if "choices" in obj and isinstance(obj["choices"], (list, tuple)) and obj["choices"]:
                first = obj["choices"][0]
                if isinstance(first, dict):
                    for key in ("content", "message", "text"):
                        if key in first and first[key]:
                            if isinstance(first[key], dict) and "content" in first[key]:
                                return str(first[key]["content"])
                            return str(first[key])
    except Exception:
        pass

    # Fallback: try string conversion
    try:
        return str(obj)
    except Exception:
        return ""


def _call_gemini(model: str, system_prompt: str, user_prompt: str, model_params: Optional[Dict[str, Any]] = None) -> str:
    if genai is None:
        raise ImportError("google-genai package not installed. Install with: pip install google-genai")
    client = genai.Client()
    # build contents as combined system+user (Gemini SDK expects `contents` or similar)
    contents = f"{system_prompt}\n\n{user_prompt}"
    # model_params mapping for gemini: the google-genai API may accept e.g. temperature, max_output_tokens etc.
    # We'll forward kwargs as-is via **model_params if provided.
    kwargs = {"model": model, "contents": contents}
    if model_params:
        kwargs.update(model_params)
    response = client.models.generate_content(**kwargs)
    return _extract_text_from_response(response)


def _call_openai(model: str, system_prompt: str, user_prompt: str, model_params: Optional[Dict[str, Any]] = None) -> str:
    if OpenAI is None:
        raise ImportError(
            "openai package not installed or incompatible. Install official OpenAI python package "
            "(newer SDK that exposes OpenAI class) with: pip install openai"
        )
    # The OpenAI client picks up API key from environment (OPENAI_API_KEY) if present.
    client = OpenAI()
    # Compose messages standard chat format
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    # default params
    params = {"model": model, "messages": messages}
    if model_params:
        params.update(model_params)
    # call chat completions create
    response = client.chat.completions.create(**params)
    return _extract_text_from_response(response)


def _call_ollama(model: str, system_prompt: str, user_prompt: str, model_params: Optional[Dict[str, Any]] = None) -> str:
    """
    Use ollama.Client if available; otherwise raise helpful error.
    Ollama API in python supports client.chat(...) which typically accepts messages list.
    We'll attempt to call client.chat(model=model, messages=[...], **model_params)
    """
    if OllamaClient is None:
        raise ImportError("ollama package not installed. Install with: pip install ollama-python")
    # Create client - If Ollama python client supports host/headers from env we can allow that:
    ollama_host = os.environ.get("OLLAMA_HOST", None)
    ollama_headers_raw = os.environ.get("OLLAMA_HEADERS", None)
    headers = None
    if ollama_headers_raw:
        # expect JSON-ish "k:v,k2:v2" or leave empty; keep simple
        try:
            headers = dict(pair.split(":", 1) for pair in ollama_headers_raw.split(","))
        except Exception:
            headers = None
    if ollama_host:
        client = OllamaClient(host=ollama_host, headers=headers)
    else:
        client = OllamaClient()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    kwargs = {"model": model, "messages": messages}
    if model_params:
        kwargs.update(model_params)
    response = client.chat(**kwargs)
    return _extract_text_from_response(response)


_PROVIDER_CALLERS = {
    "gemini": _call_gemini,
    "openai": _call_openai,
    "ollama": _call_ollama,
}


def generate_text(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    model_params: Optional[Dict[str, Any]] = None,
    *,
    max_retries: int = 3,
    rate_limit_per_minute: Optional[int] = None,
    max_backoff_seconds: int = 60,
    retry_exceptions: Optional[tuple] = None,
) -> str:
    """
    Generate text using specified provider.

    Args:
        provider: 'gemini' | 'openai' | 'ollama' (case-insensitive)
        model: model name to use
        system_prompt: system prompt string
        user_prompt: user prompt string
        model_params: optional dict of model parameters (temperature, max_tokens, etc.)
        max_retries: number of attempts (default=3)
        rate_limit_per_minute: optional rate limit (queries per minute). Default None (no limit).
        max_backoff_seconds: maximum backoff seconds between retries
        retry_exceptions: tuple of exception classes to treat as retryable (defaults to Exception)

    Returns:
        assistant reply as string (may be empty string on failure)
    Raises:
        ValueError for unknown provider
        ImportError if provider's package is missing
    """
    if not provider:
        raise ValueError("provider must be provided")
    provider_key = provider.strip().lower()
    if provider_key not in _PROVIDER_CALLERS:
        raise ValueError(f"Unknown provider: {provider}")

    caller = _PROVIDER_CALLERS[provider_key]
    rate_limiter = RateLimiter(rate_limit_per_minute)
    retry_exceptions = retry_exceptions or (Exception,)

    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("Attempt %d for provider=%s model=%s", attempt, provider_key, model)
            # Respect rate limiter BEFORE making external call
            rate_limiter.acquire()
            result = caller(model=model, system_prompt=system_prompt, user_prompt=user_prompt, model_params=model_params)
            # some callers may return bytes or non-str; coerce
            text = str(result) if result is not None else ""
            return text
        except retry_exceptions as exc:
            last_exception = exc
            logger.warning("LLM call failed on attempt %d/%d: %s", attempt, max_retries, exc, exc_info=True)
            if attempt == max_retries:
                break
            # Exponential backoff with jitter
            backoff = min(max_backoff_seconds, (2 ** (attempt - 1)) + random.uniform(0, 1.0) * (attempt))
            logger.debug("Sleeping for backoff %.3f seconds before retrying", backoff)
            time.sleep(backoff)
    # If we are here, all retries failed
    logger.error("All retries failed for provider=%s model=%s; last error: %s", provider, model, last_exception)
    # Reraise last exception to make failure explicit to caller
    if last_exception:
        raise last_exception
    return ""
