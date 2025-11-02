import os
import pytest
from dotenv import load_dotenv
from vocabgen.provider.factory import create_provider


load_dotenv()

RUN_SLOW_INTEGRATION_TESTS = os.getenv("RUN_SLOW_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_SLOW_INTEGRATION_TESTS,
                    reason="Integration tests disabled (set RUN_SLOW_INTEGRATION_TESTS=1 to enable)")
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
def test_gemini_integration_quick():
    config = {
        "provider": "gemini",
        "options": {
            "model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            "rate_limit_per_minute": 60,
        },
    }
    provider = create_provider("llm", config)
    resp = provider.generate("You are helpful", "Say 'integration test'.")
    assert "integration test" in resp.lower()
