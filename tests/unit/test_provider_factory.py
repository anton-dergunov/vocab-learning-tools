from unittest.mock import patch, MagicMock
from vocabgen.provider_factory import create_provider


@patch("importlib.import_module")
def test_create_provider_loads_class(mock_import_module):
    mock_class = MagicMock()
    mock_module = MagicMock()
    mock_module.KokoroProvider = mock_class
    mock_import_module.return_value = mock_module

    config = {"provider": "kokoro", "options": {"lang_code": "en"}}
    provider = create_provider("tts", config)

    mock_import_module.assert_called_once_with("tts.kokoro")
    mock_class.assert_called_once_with({"lang_code": "en"})
    assert provider == mock_class()
