from .base import TTSProvider
from kokoro import KPipeline
from .helpers import wrap_audio_with_silence, save_audio_to_mp3_file


class KokoroProvider(TTSProvider):
    # TODO double chech type of config
    def __init__(self, config: dict):
        self.pipeline = KPipeline(config["lang_code"], device=config.get("device"))
        self.config = config

    def synthesize(self, text: str, output_path: str) -> None:
        # TODO Randomly use a voice from the available list (https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
        generator = self.pipeline(
            text,
            voice=self.config.get("voice"),
            speed=self.config.get("speed", 1))
        _, _, audio = next(generator)

        audio = wrap_audio_with_silence(audio)
        save_audio_to_mp3_file(audio, output_path)
