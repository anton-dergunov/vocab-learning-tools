from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class LLMProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.model = config.get("model")
        self.model_params = config.get("model_params", {})
        self.rate_limit_per_minute = config.get("rate_limit_per_minute")

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate text for a given prompt."""
        pass
