import logging
from typing import Dict, Any
from .base import LLMProvider
from ..provider.rate_limiter import RateLimiter
from ..provider.retry import retry

try:
    from google import genai  # type: ignore
except Exception:
    genai = None  # type: ignore

logger = logging.getLogger("llm.gemini")


class GeminiProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if genai is None:
            raise ImportError("google-genai not installed. pip install google-genai")

        self.client = genai.Client()
        self.rate_limiter = RateLimiter(self.rate_limit_per_minute)

    @retry(max_retries=3, max_backoff_seconds=5)
    def generate(self, user_prompt: str) -> str:
        self.rate_limiter.acquire()

        contents = f"{self.system_prompt}\n\n{user_prompt}"
        kwargs = {"model": self.model, "contents": contents}
        kwargs.update(self.model_params or {})

        resp = self.client.models.generate_content(**kwargs)
        return str(resp.text)
