import os

import pytest
from vocabgen.tts.kokoro import KokoroProvider

RUN_SLOW_INTEGRATION_TESTS = os.getenv("RUN_SLOW_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.integration
@pytest.mark.skipif(
    not RUN_SLOW_INTEGRATION_TESTS,
    reason="Integration tests disabled (set RUN_SLOW_INTEGRATION_TESTS=true to enable)",
)
def test_kokoro_generate_audio(tmp_path):
    config = {
        "lang_code": "e",
        "voice": "ef_dora",
        "speed": 1.0
    }

    provider = KokoroProvider(config)
    output_file = tmp_path / "test.mp3"
    provider.synthesize("Añoro mi hogar.", str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 1000  # should not be empty
