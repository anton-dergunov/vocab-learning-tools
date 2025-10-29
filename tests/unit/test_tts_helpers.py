import numpy as np
from unittest.mock import patch, MagicMock
from vocabgen.tts.helpers import wrap_audio_with_silence, SILENCE, save_audio_to_mp3_file

def test_wrap_audio_with_silence():
    audio = np.ones(3)
    result = wrap_audio_with_silence(audio)
    assert np.array_equal(result[: len(SILENCE)], SILENCE)
    assert np.array_equal(result[-len(SILENCE):], SILENCE)
    assert np.array_equal(result[len(SILENCE):-len(SILENCE)], audio)


@patch("vocabgen.tts.helpers.sf.write")
@patch("vocabgen.tts.helpers.AudioSegment")
def test_save_audio_to_mp3_file(mock_audio_segment, mock_sf_write):
    audio_mock = MagicMock()
    filename = "output.mp3"

    save_audio_to_mp3_file(audio_mock, filename)

    mock_sf_write.assert_called_once()
    mock_audio_segment.from_file.assert_called_once()
    mock_audio_segment.from_file.return_value.export.assert_called_once_with(filename, format="mp3")
