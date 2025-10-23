import os
import tempfile
from pathlib import Path
import json
import pytest
from unittest.mock import patch


# Ensure we can import the script module (it uses sys.path hack internally)
import scripts.clean_vocab as clean_vocab_script


@pytest.fixture(autouse=True)
def tmp_env(tmp_path, monkeypatch):
    # create temporary config and prompt
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "defaults.toml"
    cfg_path.write_text(
        """
[inbox]
path = "{inbox}"

[llm]
provider = "gemini"
model = "fake-model"
max_retries = 1

[processing]
batch_size = 1
prompt = "{prompt}"
show_items = true
""".format(
            inbox=str(tmp_path / "inbox.md"), prompt=str(tmp_path / "prompt.txt")
        )
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("EXAMPLE PROMPT")
    inbox = tmp_path / "inbox.md"
    # create two sections separated by ---:
    inbox.write_text("el saco - coat\n---\nni en pedo - no way\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def fake_generate_text(provider, model, system_prompt, user_prompt, model_params, max_retries, rate_limit_per_minute):
    # For each batch (one section), return a canned response that includes Topic and title
    if "saco" in user_prompt:
        return "##### **el saco** 🧥\n*coat; jacket*\n> ¡Qué **saco** tan lindo! - What a nice **jacket**!\nTopic: Appearance\n"
    else:
        return "##### **ni en pedo** 🚫\n*no way*\n> **Ni en pedo** te venís a mi casa. - **No way** you're coming to my house.\nTopic: Slang\n"


def test_clean_vocab_flow(tmp_path, monkeypatch):
    # monkeypatch LLM
    with patch("vocabgen.llm_client.generate_text", side_effect=fake_generate_text):
        # run the script main
        clean_vocab_script.main(argv=["--config", str(tmp_path / "config" / "defaults.toml")])
        # check topic files were created
        food_file = tmp_path / ("Appearance" + DEFAULT_GEN_SUFFIX)
        slang_file = tmp_path / ("Slang" + DEFAULT_GEN_SUFFIX)
        assert food_file.exists()
        assert slang_file.exists()
        # ensure inbox has been emptied
        inbox = tmp_path / "inbox.md"
        content = inbox.read_text()
        assert content.strip() == ""
        # check contents include titles
        assert "el saco" in food_file.read_text()
        assert "ni en pedo" in slang_file.read_text()
