from unittest.mock import MagicMock
from vocabgen.provider.factory import create_provider


def test_ollama_generate_mock(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.message.content = "hello from ollama"
    fake_client = MagicMock()
    fake_client.chat.return_value = fake_resp

    monkeypatch.setattr(
        "vocabgen.llm.ollama.OllamaClient",
        lambda *a, **kw: fake_client
    )

    config = {
        "provider": "ollama",
        "options": {
            "model": "gemma3",
            "rate_limit_per_minute": 60,
        },
    }
    provider = create_provider("llm", config)
    out = provider.generate("system", "user")

    assert "hello from ollama" in out
