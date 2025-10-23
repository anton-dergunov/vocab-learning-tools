import pytest
from pathlib import Path
from unittest.mock import patch
import scripts.clean_vocab as clean_vocab_script


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    """
    Create temporary config, inbox, and prompt files matching the new schema.
    """
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("EXAMPLE PROMPT")

    inbox_path = tmp_path / "inbox.md"
    inbox_path.write_text("el saco - coat\n\n---\n\nni en pedo - no way\n")

    # Create output pattern directory (files will be created per topic)
    out_pattern = str(tmp_path / "Spanish vocab - %topic.md")

    cfg_path = cfg_dir / "defaults.toml"
    cfg_path.write_text(
        f"""
[vocabulary]
language = "Spanish"
topics = ["Emotions", "Actions", "Nature", "Culture", "Food",
          "Health", "Appearance", "Technology", "Travel", "Slang", "Misc"]

[files]
inbox = "{inbox_path}"
output_pattern = "{out_pattern}"

[llm]
provider = "gemini"
model = "fake-model"
model_params = {{}}
prompt_path = "{prompt_path}"
max_retries = 1
rate_limit_per_minute = 5

[processing]
batch_size = 1
show_items = true
"""
    )

    monkeypatch.chdir(tmp_path)
    return tmp_path


def fake_generate_text(provider, model, system_prompt, user_prompt, model_params, max_retries, rate_limit_per_minute):
    """
    Fake LLM call that returns a clean, formatted vocabulary article depending on input.
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


def test_clean_vocab_flow(tmp_path, monkeypatch):
    """
    End-to-end test for CLI script using mocked LLM and temporary files.
    """
    with patch("vocabgen.llm_client.generate_text", side_effect=fake_generate_text):
        cfg_file = tmp_path / "config" / "defaults.toml"
        clean_vocab_script.main(argv=["--config", str(cfg_file)])

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
