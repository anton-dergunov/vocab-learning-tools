from pathlib import Path
from unittest.mock import patch

import scripts.generate_anki_deck_draft as anki_script


REPOSITORY_ROOT = Path(__file__).parents[2]


def test_resolve_project_path_is_independent_of_working_directory(tmp_path):
    assert anki_script.resolve_project_path("templates", tmp_path) == (
        tmp_path / "templates"
    )
    absolute = tmp_path / "article.json"
    assert anki_script.resolve_project_path(absolute, Path("/unused")) == absolute


def test_preview_command_runs_from_another_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "preview" / "anhelar.html"

    result = anki_script.main(
        [
            "preview",
            str(REPOSITORY_ROOT / "input.json"),
            "--output",
            str(output),
        ]
    )

    assert result == output
    assert output.is_file()
    assert "anhelar" in output.read_text(encoding="utf-8")


class FakeProvider:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def synthesize(self, text: str, output_path: str) -> None:
        self.calls.append((text, Path(output_path)))
        Path(output_path).write_bytes(self.payload)


def test_build_command_uses_factory_cache_and_stable_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = tmp_path / "cache"
    output = tmp_path / "decks" / "anhelar.apkg"
    config = tmp_path / "local.yaml"
    config.write_text(
        f"""anki:
  cache_dir: "{cache}"
  output_dir: "{tmp_path / 'decks'}"
""",
        encoding="utf-8",
    )
    images = FakeProvider(b"image")
    audio = FakeProvider(b"audio")

    def provider_for(family, provider_config):
        return images if family == "vision" else audio

    with patch(
        "vocabgen.provider.factory.create_provider",
        side_effect=provider_for,
    ) as create_provider:
        result = anki_script.main(
            [
                "build",
                str(REPOSITORY_ROOT / "input.json"),
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )

    assert result == output
    assert output.is_file()
    assert [call.args[0] for call in create_provider.call_args_list] == [
        "tts",
        "vision",
    ]
    assert len(images.calls) == 5
    assert len(audio.calls) == 5
    assert len(list((cache / "images").glob("*.jpg"))) == 5
    assert len(list((cache / "audio").glob("*.mp3"))) == 5
