import os
import logging
from typing import Dict, Any
from .base import LLMProvider
from ..provider.rate_limiter import RateLimiter
from ..provider.retry import retry

try:
    from ollama import Client as OllamaClient
except Exception:
    OllamaClient = None

logger = logging.getLogger("llm.ollama")


class OllamaProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if OllamaClient is None:
            raise ImportError("ollama-python not installed. pip install ollama-python")

        host = os.environ.get("OLLAMA_HOST")
        self.client = OllamaClient(host=host) if host else OllamaClient()
        self.rate_limiter = RateLimiter(self.rate_limit_per_minute)

    @retry(max_retries=3, max_backoff_seconds=5)
    def generate(self, user_prompt: str) -> str:
        self.rate_limiter.acquire()

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        params = {"model": self.model, "messages": messages}
        params.update(self.model_params or {})

        resp = self.client.chat(**params)
        return str(resp.message.content)
