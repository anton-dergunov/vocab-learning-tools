import torch
from PIL import Image
from diffusers import StableDiffusionPipeline

from .base import ImageProvider


DEFAULT_WIDTH = 384
DEFAULT_HEIGHT = 384


def select_device(requested_device: str | None = None) -> str:
    """Resolve an explicit device or choose the best available local backend."""
    if requested_device and requested_device != "auto":
        return requested_device
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class StableDiffusionProvider(ImageProvider):
    # TODO double chech type of config
    def __init__(self, config: dict):
        self.device = select_device(config.get("device"))
        dtype = torch.float32 if self.device == "cpu" else torch.float16
        self.pipeline = StableDiffusionPipeline.from_pretrained(
            config.get("model_id"),
            torch_dtype=dtype,
        )
        self.pipeline = self.pipeline.to(self.device)
        self.config = config

    def synthesize(self, text: str, output_path: str) -> None:
        image = self.pipeline(
            text,
            **self.config.get("generation_params", {}),
        ).images[0]

        max_size=(self.config.get("width", DEFAULT_WIDTH), self.config.get("height", DEFAULT_HEIGHT))
        image = image.resize(max_size, Image.LANCZOS)  # LANCZOS = high-quality downsampling

        image.save(output_path)
