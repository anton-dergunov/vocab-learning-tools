from unittest.mock import MagicMock
from vocabgen.provider.factory import create_provider


def test_gemini_generate_mock(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.text = "hello from gemini"

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp

    monkeypatch.setattr(
        "vocabgen.llm.gemini.genai",
        MagicMock(Client=MagicMock(return_value=fake_client))
    )

    config = {
        "provider": "gemini",
        "options": {
            "model": "gemini-test",
            "rate_limit_per_minute": 60,
        },
    }
    provider = create_provider("llm", config)
    out = provider.generate("system", "user")

    assert "hello from gemini" in out
