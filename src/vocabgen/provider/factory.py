import importlib


# TODO Consider supporting other TTS
# https://cloud.google.com/text-to-speech?hl=en
# https://useapi.net/
# https://elevenlabs.io/voice-design
# https://platform.openai.com/docs/guides/text-to-speech
# https://github.com/travisvn/openai-edge-tts
# https://aws.amazon.com/polly/


# TODO Type annotations
# Also can define the exact types of providers as kind of enum?
def create_provider(type: str, config: dict):
    provider_name = config["provider"]
    options = config.get("options", {})

    module_name = f"vocabgen.{type}.{provider_name}"
    class_name = "".join(word.capitalize() for word in provider_name.split("_")) + "Provider"

    module = importlib.import_module(module_name)
    provider_class = getattr(module, class_name)
    # TODO Is it better to pass arguments as options or **options
    return provider_class(options)
