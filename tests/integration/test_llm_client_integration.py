import os
import pytest
from dotenv import load_dotenv
import vocabgen.llm_client as llm_client

load_dotenv()


RUN_HEAVY_INTEGRATION_TESTS = os.getenv("RUN_HEAVY_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_HEAVY_INTEGRATION_TESTS,
                    reason="Integration tests disabled (set RUN_HEAVY_INTEGRATION_TESTS=1 to enable)")
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"),
                    reason="GEMINI_API_KEY not set")
def test_gemini_integration_quick():
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    resp = llm_client.generate_text(
        provider="gemini",
        model=model,
        system_prompt="You are a helpful assistant.",
        user_prompt="Say 'integration test' briefly.",
        max_retries=2,
        rate_limit_per_minute=60,
    )
    assert "integration test" in resp.lower()


@pytest.mark.integration
@pytest.mark.skipif(not RUN_HEAVY_INTEGRATION_TESTS,
                    reason="Integration tests disabled (set RUN_HEAVY_INTEGRATION_TESTS=1 to enable)")
@pytest.mark.skipif(llm_client.OllamaClient is None,
                    reason="Ollama client not installed")
def test_ollama_integration_quick():
    model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    resp = llm_client.generate_text(
        provider="ollama",
        model=model,
        system_prompt="You are a helpful assistant.",
        user_prompt="Say 'ollama integration' in one short sentence.",
        max_retries=2,
        rate_limit_per_minute=60,
    )
    assert "ollama integration" in resp.lower()
