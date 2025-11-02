from unittest.mock import MagicMock
from vocabgen.provider.factory import create_provider


def test_openai_generate(monkeypatch):
    fake_choice = MagicMock()
    fake_choice.message.content = "hello from openai"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = fake_response

    monkeypatch.setattr("vocabgen.llm.openai.OpenAI", lambda: mock_openai)

    config = {
        "provider": "openai",
        "options": {
            "model": "gpt-test",
            "rate_limit_per_minute": 60,
        },
    }
    provider = create_provider("llm", config)
    out = provider.generate("system", "user")

    assert "hello from openai" in out
