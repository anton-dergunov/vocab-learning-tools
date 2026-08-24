#!/usr/bin/env python3
"""
Manual LLM testing CLI.

Usage:
    python scripts/test_llm_manual.py --system "You are helpful" --user "Say hello!"
"""

import argparse
from pathlib import Path

from vocabgen.config import load_config, select_llm_provider
from vocabgen.provider.factory import create_provider


_REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description="Manual LLM text generation.")
    parser.add_argument("--system", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--provider", required=False)
    parser.add_argument("--model", required=False, default=None)
    parser.add_argument(
        "--config",
        required=False,
        help="Optional YAML file merged over config/defaults.yaml",
    )
    args = parser.parse_args()

    config = load_config(
        _REPO_ROOT / "config/defaults.yaml",
        args.config,
    )
    provider_name, _, provider_cfg = select_llm_provider(config, args.provider)
    if args.model:
        provider_cfg["options"]["model"] = args.model

    provider = create_provider("llm", provider_cfg)
    print(f"Generating with {provider_name}...\n")
    output = provider.generate(args.system, args.user)
    print("\nResponse:\n──────────────────────────\n")
    print(output)


if __name__ == "__main__":
    main()
