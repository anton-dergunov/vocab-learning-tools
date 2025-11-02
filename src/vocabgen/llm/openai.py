import logging
from typing import Dict, Any
from .base import LLMProvider
from ..provider.rate_limiter import RateLimiter
from ..provider.retry import retry

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logger = logging.getLogger("llm.openai")


class OpenaiProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if OpenAI is None:
            raise ImportError("OpenAI package missing. Install with: pip install openai")

        self.client = OpenAI()
        self.rate_limiter = RateLimiter(self.rate_limit_per_minute)

    @retry()
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.rate_limiter.acquire()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        params = {"model": self.model, "messages": messages}
        params.update(self.model_params or {})

        resp = self.client.chat.completions.create(**params)
        return str(resp.choices[0].message.content)
