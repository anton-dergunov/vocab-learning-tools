import torch
from PIL import Image
from diffusers import StableDiffusionPipeline

from .base import ImageProvider


DEFAULT_WIDTH = 384
DEFAULT_HEIGHT = 384


class StableDiffusionProvider(ImageProvider):
    # TODO double chech type of config
    def __init__(self, config: dict):
        self.pipeline = StableDiffusionPipeline.from_pretrained(config.get("model_id"), torch_dtype=torch.float16)
        # TODO Get default device?
        self.pipeline = self.pipeline.to(config.get("device"))
        self.config = config

    def synthesize(self, text: str, output_path: str) -> None:
        # TODO Consider these arguments:
        # output = pipe(prompt, height=height, width=width, num_inference_steps=num_inference_steps, guidance_scale=guidance_scale)
        image = self.pipeline(text).images[0]

        max_size=(self.config.get("width", DEFAULT_WIDTH), self.config.get("height", DEFAULT_HEIGHT))
        image = image.resize(max_size, Image.LANCZOS)  # LANCZOS = high-quality downsampling

        image.save(output_path)
