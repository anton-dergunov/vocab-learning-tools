import torch
from PIL import Image
from unittest.mock import patch, MagicMock

from vocabgen.vision.stable_diffusion import StableDiffusionProvider


@patch("vocabgen.vision.stable_diffusion.StableDiffusionPipeline")
def test_stable_diffusion_provider_synthesize(mock_sd_pipeline):
    # Setup mock pipeline
    mock_pipeline_instance = MagicMock()
    mock_sd_pipeline.from_pretrained.return_value = mock_pipeline_instance
    mock_pipeline_instance.to.return_value = mock_pipeline_instance

    # Setup mock image
    mock_image = MagicMock(spec=Image.Image)
    mock_pipeline_instance.return_value = MagicMock(images=[mock_image])
    mock_image.resize.return_value = mock_image

    # Create provider and call synthesize
    config = {
        "model_id": "test_model",
        "device": "cuda",
        "width": 384,
        "height": 384
    }
    provider = StableDiffusionProvider(config)
    provider.synthesize("test prompt", "output.png")

    # Verify calls
    mock_sd_pipeline.from_pretrained.assert_called_once_with("test_model", torch_dtype=torch.float16)
    mock_pipeline_instance.to.assert_called_once_with("cuda")
    mock_pipeline_instance.assert_called_once_with("test prompt")
    mock_image.resize.assert_called_once_with((384, 384), Image.LANCZOS)
    mock_image.save.assert_called_once_with("output.png")
