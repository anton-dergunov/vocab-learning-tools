from pathlib import Path

from box import Box

import pytest

from vocabgen.config import deep_merge, load_config, select_llm_provider


REPOSITORY_ROOT = Path(__file__).parents[2]


def test_deep_merge_preserves_nested_defaults():
    defaults = {
        "files": {"inbox": "data/inbox.md", "output_pattern": "data/%topic.md"},
        "processing": {"batch_size": 1},
    }
    overrides = {"files": {"inbox": "/local/inbox.md"}}

    merged = deep_merge(defaults, overrides)

    assert merged == {
        "files": {
            "inbox": "/local/inbox.md",
            "output_pattern": "data/%topic.md",
        },
        "processing": {"batch_size": 1},
    }
    assert defaults["files"]["inbox"] == "data/inbox.md"


def test_load_config_merges_local_overlay(tmp_path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(
        "files:\n  inbox: data/inbox.md\n  output_pattern: data/%topic.md\n",
        encoding="utf-8",
    )
    local = tmp_path / "local.yaml"
    local.write_text("files:\n  inbox: /local/inbox.md\n", encoding="utf-8")

    config = load_config(defaults, local)

    assert config.files.inbox == "/local/inbox.md"
    assert config.files.output_pattern == "data/%topic.md"


def test_select_llm_provider_uses_default():
    config = Box(
        {
            "llm": {
                "default_provider": "gemini",
                "providers": {
                    "gemini": {"options": {"model": "gemini-model"}},
                    "ollama": {"options": {"model": "local-model"}},
                },
            }
        }
    )

    name, provider_config = select_llm_provider(config)

    assert name == "gemini"
    assert provider_config == {
        "provider": "gemini",
        "options": {"model": "gemini-model"},
    }


def test_select_llm_provider_allows_cli_override():
    config = Box(
        {
            "llm": {
                "default_provider": "gemini",
                "providers": {
                    "gemini": {"options": {"model": "gemini-model"}},
                    "ollama": {
                        "options": {"model": "local-model"},
                    },
                },
            }
        }
    )

    name, provider_config = select_llm_provider(config, "ollama")

    assert name == "ollama"
    assert provider_config == {
        "provider": "ollama",
        "options": {"model": "local-model"},
    }


def test_select_llm_provider_rejects_unknown_provider():
    config = Box(
        {
            "llm": {
                "default_provider": "gemini",
                "providers": {"gemini": {"options": {}}},
            }
        }
    )

    with pytest.raises(ValueError, match="Unknown LLM provider 'missing'"):
        select_llm_provider(config, "missing")


def test_default_media_settings_preserve_provider_decisions():
    config = load_config(REPOSITORY_ROOT / "config" / "defaults.yaml")

    assert config.tts.options.lang_code == "e"
    assert config.tts.options.voice == "ef_dora"
    assert config.image.options.width == 384
    assert config.image.options.height == 384
