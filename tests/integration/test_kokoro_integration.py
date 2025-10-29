import pytest
from vocabgen.tts.kokoro import KokoroProvider


@pytest.mark.integration
def test_kokoro_generate_audio(tmp_path):
    config = {
        "lang_code": "e",
        "voice": "ef_dora",
        "speed": 1.0
    }

    provider = KokoroProvider(config)
    output_file = tmp_path / "test.mp3"
    provider.synthesize("Integration test: Hello, world!", str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 1000  # should not be empty
