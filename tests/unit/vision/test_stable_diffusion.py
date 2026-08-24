import torch
from PIL import Image
from unittest.mock import patch, MagicMock

from vocabgen.vision.stable_diffusion import StableDiffusionProvider, select_device


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
        "height": 384,
        "generation_params": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
        },
    }
    provider = StableDiffusionProvider(config)
    provider.synthesize("test prompt", "output.png")

    # Verify calls
    mock_sd_pipeline.from_pretrained.assert_called_once_with("test_model", torch_dtype=torch.float16)
    mock_pipeline_instance.to.assert_called_once_with("cuda")
    mock_pipeline_instance.assert_called_once_with(
        "test prompt",
        num_inference_steps=25,
        guidance_scale=7.5,
    )
    mock_image.resize.assert_called_once_with((384, 384), Image.LANCZOS)
    mock_image.save.assert_called_once_with("output.png")


@patch("vocabgen.vision.stable_diffusion.torch.cuda.is_available", return_value=False)
@patch("vocabgen.vision.stable_diffusion.torch.backends.mps.is_available", return_value=True)
def test_select_device_prefers_mps(mock_mps, mock_cuda):
    assert select_device("auto") == "mps"
    mock_cuda.assert_not_called()


@patch("vocabgen.vision.stable_diffusion.torch.cuda.is_available", return_value=False)
@patch("vocabgen.vision.stable_diffusion.torch.backends.mps.is_available", return_value=False)
def test_select_device_falls_back_to_cpu(mock_mps, mock_cuda):
    assert select_device() == "cpu"


def test_select_device_respects_explicit_value():
    assert select_device("cuda:1") == "cuda:1"
