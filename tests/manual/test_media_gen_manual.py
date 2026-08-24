#!/usr/bin/env python3
"""
Media generation test script.

Usage:
    python test_media_gen_manual.py --type tts --config config/defaults.yaml \
        --text "Hello world" --output out.mp3
"""

import argparse
import tempfile
from pathlib import Path

from vocabgen.config import load_config
from vocabgen.provider.factory import create_provider


_REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="Generate media (audio or image) from text.")
    parser.add_argument(
        "--type",
        required=True,
        choices=["tts", "vision"],
        help="Type of provider to use: 'tts' for text-to-speech or 'vision' for image generation.",
    )
    parser.add_argument(
        "--config",
        help="Optional YAML file merged over config/defaults.yaml.",
    )
    parser.add_argument(
        "--text",
        required=True,
        help="Input text to synthesize or visualize.",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path. If omitted, a temporary file will be used.",
    )

    args = parser.parse_args()

    all_config = load_config(_REPO_ROOT / "config/defaults.yaml", args.config)
    if args.type not in all_config:
        raise KeyError(f"Config file does not contain section '{args.type}'.")
    config = all_config[args.type].to_dict()

    # Create provider
    provider = create_provider(args.type, config)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        suffix = ".mp3" if args.type == "tts" else ".jpg"
        output_path = Path(tempfile.gettempdir()) / f"generated_output{suffix}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate media
    print(f"Generating {args.type} output to {output_path} ...")
    provider.synthesize(args.text, str(output_path))
    print(f"Media saved to {output_path}")


if __name__ == "__main__":
    main()
