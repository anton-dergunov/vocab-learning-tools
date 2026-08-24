import pytest
from pathlib import Path
from unittest.mock import patch
import scripts.clean_vocab as clean_vocab_script


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    """
    Create a temporary YAML config, inbox, and prompt files matching the new schema.
    """
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("EXAMPLE PROMPT")

    inbox_path = tmp_path / "inbox.md"
    inbox_path.write_text("el saco - coat\n\n---\n\nni en pedo - no way\n")

    # Create output pattern directory (files will be created per topic)
    out_pattern = str(tmp_path / "Spanish vocab - %topic.md")

    # ✅ YAML version of config
    cfg_path = cfg_dir / "defaults.yaml"
    cfg_path.write_text(
        f"""
vocabulary:
  language: "Spanish"
  topics:
    - "Emotions"
    - "Actions"
    - "Nature"
    - "Culture"
    - "Food"
    - "Health"
    - "Appearance"
    - "Technology"
    - "Travel"
    - "Slang"
    - "Misc"

files:
  inbox: "{inbox_path}"
  output_pattern: "{out_pattern}"

llm:
  default_provider: "gemini"
  prompt_path: "{prompt_path}"
  providers:
    gemini:
      options:
        model: "fake-model"
        model_params: {{}}
        rate_limit_per_minute: 5
    ollama:
      options:
        model: "gemma3:4b"
        model_params: {{}}
        rate_limit_per_minute: 60

processing:
  batch_size: 1
  show_items: true
"""
    )

    monkeypatch.chdir(tmp_path)
    return tmp_path


def fake_generate(self, system_prompt: str, user_prompt: str) -> str:
    """
    Fake provider call that returns a clean, formatted vocabulary article
    depending on the input prompt content.
    """
    if "saco" in user_prompt:
        return """##### **el saco** 🧥
*coat; jacket*
> ¡Qué **saco** tan lindo! - What a nice **jacket**!
Topic: Appearance
"""
    else:
        return """##### **ni en pedo** 🚫
*no way*
> **Ni en pedo** te venís a mi casa. - **No way** you're coming to my house.
Topic: Slang
"""


class FakeLLMProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return fake_generate(self, system_prompt, user_prompt)


class FailingLLMProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("LLM unavailable")


class MalformedLLMProvider:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "This is not a vocabulary article."


class OneSuccessThenFailureProvider:
    def __init__(self):
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return fake_generate(self, system_prompt, user_prompt)
        raise RuntimeError("second batch failed")


def test_clean_vocab_flow(tmp_path, monkeypatch):
    """
    End-to-end test for CLI script using mocked LLM provider and temporary files.
    """
    with patch(
        "scripts.clean_vocab.create_provider",
        return_value=FakeLLMProvider(),
    ) as create_provider:
        cfg_file = tmp_path / "config" / "defaults.yaml"
        clean_vocab_script.main(argv=["--config", str(cfg_file)])

        create_provider.assert_called_once_with(
            "llm",
            {
                "provider": "gemini",
                "options": {
                    "model": "fake-model",
                    "model_params": {},
                    "rate_limit_per_minute": 5,
                },
            },
        )

        # Verify topic files exist
        appearance_file = tmp_path / "Spanish vocab - Appearance.md"
        slang_file = tmp_path / "Spanish vocab - Slang.md"
        assert appearance_file.exists()
        assert slang_file.exists()

        # Inbox should be emptied after processing
        inbox = tmp_path / "inbox.md"
        assert inbox.read_text().strip() == ""

        # Check contents include generated articles
        appearance_text = appearance_file.read_text()
        slang_text = slang_file.read_text()

        assert "el saco" in appearance_text
        assert "ni en pedo" in slang_text

        # Sanity check: both contain Topic lines stripped from articles
        assert not any("Topic:" in line for line in appearance_text.splitlines())
        assert not any("Topic:" in line for line in slang_text.splitlines())


def test_clean_vocab_allows_llm_provider_override(tmp_path):
    with patch(
        "scripts.clean_vocab.create_provider",
        return_value=FakeLLMProvider(),
    ) as create_provider:
        cfg_file = tmp_path / "config" / "defaults.yaml"
        clean_vocab_script.main(
            argv=[
                "--config",
                str(cfg_file),
                "--llm-provider",
                "ollama",
            ]
        )

        create_provider.assert_called_once_with(
            "llm",
            {
                "provider": "ollama",
                "options": {
                    "model": "gemma3:4b",
                    "model_params": {},
                    "rate_limit_per_minute": 60,
                },
            },
        )


def test_llm_failure_leaves_inbox_unchanged(tmp_path):
    inbox = tmp_path / "inbox.md"
    original = inbox.read_text()

    with patch(
        "scripts.clean_vocab.create_provider",
        return_value=FailingLLMProvider(),
    ):
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            clean_vocab_script.main(
                argv=["--config", str(tmp_path / "config" / "defaults.yaml")]
            )

    assert inbox.read_text() == original


def test_malformed_llm_output_leaves_inbox_unchanged(tmp_path):
    inbox = tmp_path / "inbox.md"
    original = inbox.read_text()

    with patch(
        "scripts.clean_vocab.create_provider",
        return_value=MalformedLLMProvider(),
    ):
        with pytest.raises(ValueError, match="Malformed LLM article"):
            clean_vocab_script.main(
                argv=["--config", str(tmp_path / "config" / "defaults.yaml")]
            )

    assert inbox.read_text() == original
    assert not list(tmp_path.glob("Spanish vocab - *.md"))


def test_output_write_failure_leaves_inbox_unchanged(tmp_path):
    inbox = tmp_path / "inbox.md"
    original = inbox.read_text()

    with (
        patch(
            "scripts.clean_vocab.create_provider",
            return_value=FakeLLMProvider(),
        ),
        patch(
            "scripts.clean_vocab.append_to_file",
            side_effect=OSError("disk full"),
        ),
    ):
        with pytest.raises(OSError, match="disk full"):
            clean_vocab_script.main(
                argv=["--config", str(tmp_path / "config" / "defaults.yaml")]
            )

    assert inbox.read_text() == original


def test_only_successful_batches_are_removed_from_inbox(tmp_path):
    inbox = tmp_path / "inbox.md"

    with patch(
        "scripts.clean_vocab.create_provider",
        return_value=OneSuccessThenFailureProvider(),
    ):
        with pytest.raises(RuntimeError, match="second batch failed"):
            clean_vocab_script.main(
                argv=["--config", str(tmp_path / "config" / "defaults.yaml")]
            )

    remaining = inbox.read_text()
    assert "el saco" not in remaining
    assert remaining == "ni en pedo - no way\n"
    assert "el saco" in (tmp_path / "Spanish vocab - Appearance.md").read_text()
