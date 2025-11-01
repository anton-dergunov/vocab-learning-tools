from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class LLMProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.model = config.get("model")
        self.system_prompt = config.get("system_prompt", "")
        self.model_params = config.get("model_params", {})
        self.max_retries = config.get("max_retries", 3)
        self.rate_limit_per_minute = config.get("rate_limit_per_minute")
        self.max_backoff_seconds = config.get("max_backoff_seconds", 60)
        # FIXME Use config instead!

    @abstractmethod
    def generate(self, user_prompt: str) -> str:
        """Generate text for a given prompt."""
        pass
