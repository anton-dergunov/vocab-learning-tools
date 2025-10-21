import os
import pytest
from dotenv import load_dotenv
import vocabgen.llm_client as llm_client

load_dotenv()


@pytest.mark.integration
def test_gemini_integration_quick():
    if os.environ.get("RUN_LLM_INTEGRATION_TESTS") != "1":
        pytest.skip("Integration tests disabled (set RUN_LLM_INTEGRATION_TESTS=1 to enable)")

    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

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
def test_ollama_integration_quick():
    if os.environ.get("RUN_LLM_INTEGRATION_TESTS") != "1":
        pytest.skip("Integration tests disabled (set RUN_LLM_INTEGRATION_TESTS=1 to enable)")

    if llm_client.OllamaClient is None:
        pytest.skip("Ollama client not installed")

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
