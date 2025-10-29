from unittest.mock import patch, MagicMock
from vocabgen.tts.kokoro import KokoroProvider


@patch("vocabgen.tts.kokoro.KPipeline")
@patch("vocabgen.tts.kokoro.wrap_audio_with_silence")
@patch("vocabgen.tts.kokoro.save_audio_to_mp3_file")
def test_kokoro_provider_synthesize(mock_save_audio, mock_wrap_audio, mock_kpipeline):
    mock_pipeline_instance = MagicMock()
    mock_kpipeline.return_value = mock_pipeline_instance
    mock_pipeline_instance.return_value = iter([(None, None, [1, 2, 3])])

    provider = KokoroProvider({"lang_code": "en", "voice": "test_voice"})
    provider.synthesize("Hello world", "out.mp3")

    mock_kpipeline.assert_called_once_with("en", device=None)
    mock_wrap_audio.assert_called_once()
    mock_save_audio.assert_called_once_with(mock_wrap_audio.return_value, "out.mp3")
