import argparse
import tempfile
from pathlib import Path
import yaml
import subprocess

from vocabgen.provider_factory import create_provider


def main():
    parser = argparse.ArgumentParser(description="Manual TTS generation test.")
    parser.add_argument("--config", type=str, default="config/defaults.yaml", help="Path to YAML config")
    parser.add_argument("--text", type=str, required=True, help="Text to synthesize")
    args = parser.parse_args()

    # Load config
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)["tts"]

    provider = create_provider("tts", config)
    output_path = Path(tempfile.gettempdir()) / "tts_output.mp3"

    print(f"Generating audio to {output_path} ...")
    provider.synthesize(args.text, str(output_path))
    print(f"Audio saved to {output_path}")

if __name__ == "__main__":
    main()
