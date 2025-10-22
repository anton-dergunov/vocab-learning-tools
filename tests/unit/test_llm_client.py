import os
import time
import pytest
from unittest.mock import MagicMock, patch
import vocabgen.llm_client as llm_client


def test_rate_limiter_allows_immediate_calls_when_unlimited():
    rl = llm_client.RateLimiter(max_calls_per_minute=None)
    start = time.time()
    rl.acquire()
    rl.acquire()
    assert time.time() - start < 0.1


def test_generate_text_uses_openai_mock():
    fake_choice = MagicMock()
    fake_choice.message.content = "hello from openai"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = fake_response

    with patch.object(llm_client, "OpenAI", return_value=mock_openai):
        resp = llm_client.generate_text(
            provider="openai",
            model="gpt-test",
            system_prompt="system",
            user_prompt="user",
            model_params={"temperature": 0.1},
            max_retries=1,
        )
        assert "hello from openai" in resp


def test_generate_text_uses_gemini_mock():
    fake_resp = MagicMock()
    fake_resp.text = "hello from gemini"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    with patch.object(llm_client, "genai", new=MagicMock(Client=MagicMock(return_value=fake_client))):
        resp = llm_client.generate_text(
            provider="gemini",
            model="gemini-test",
            system_prompt="system",
            user_prompt="user",
            max_retries=1,
        )
        assert "hello from gemini" in resp


def test_generate_text_uses_ollama_mock():
    fake_resp = MagicMock()
    fake_resp.message.content = "hello from ollama"
    fake_client = MagicMock()
    fake_client.chat.return_value = fake_resp
    with patch.object(llm_client, "OllamaClient", return_value=fake_client):
        resp = llm_client.generate_text(
            provider="ollama",
            model="gemma3",
            system_prompt="system",
            user_prompt="user",
            max_retries=1,
        )
        assert "hello from ollama" in resp


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        llm_client.generate_text(provider="nope", model="m", system_prompt="", user_prompt="", max_retries=1)
