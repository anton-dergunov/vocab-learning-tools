import os
import pytest
from vocabgen.provider.factory import create_provider


RUN_SLOW_INTEGRATION_TESTS = os.getenv("RUN_SLOW_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_SLOW_INTEGRATION_TESTS,
                    reason="Integration tests disabled (set RUN_SLOW_INTEGRATION_TESTS=1 to enable)")
def test_ollama_integration_quick():
    config = {
        "provider": "ollama",
        "options": {
            "model": os.getenv("OLLAMA_MODEL", "gemma3:4b"),
            "rate_limit_per_minute": 60,
        },
    }
    provider = create_provider("llm", config)
    resp = provider.generate("You are helpful", "Say 'ollama integration'.")
    assert "ollama integration" in resp.lower()
