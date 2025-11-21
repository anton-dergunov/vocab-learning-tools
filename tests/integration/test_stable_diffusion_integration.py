import pytest
import os
import torch
from vocabgen.vision.stable_diffusion import StableDiffusionProvider


RUN_SLOW_INTEGRATION_TESTS = os.getenv("RUN_SLOW_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_SLOW_INTEGRATION_TESTS,
                    reason="Integration tests disabled (set RUN_SLOW_INTEGRATION_TESTS=1 to enable)")
def test_stable_diffusion_generate_image(tmp_path):
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    config = {
        "model_id": "hf-internal-testing/tiny-stable-diffusion-torch",
        # "model_id": "stabilityai/sd-turbo",
        "device": device,
        "width": 100,
        "height": 100
    }

    provider = StableDiffusionProvider(config)
    output_file = tmp_path / "image.jpg"
    provider.synthesize("sunset over mountains", str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 1000  # should not be empty