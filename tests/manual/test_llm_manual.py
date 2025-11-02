#!/usr/bin/env python3
"""
Manual LLM testing CLI.

Usage:
    python scripts/test_llm_manual.py --system "You are helpful" --user "Say hello!"
"""

import argparse
import yaml
from vocabgen.provider.factory import create_provider


def main():
    parser = argparse.ArgumentParser(description="Manual LLM text generation.")
    parser.add_argument("--system", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--provider", required=False, choices=["openai", "gemini", "ollama"])
    parser.add_argument("--model", required=False, default=None)
    parser.add_argument("--config", required=False, help="YAML config path")
    # TODO Create choice of arguments
    args = parser.parse_args()

    if args.config:
        with open(args.config, "r") as f:
            cfg = yaml.safe_load(f)
            provider_cfg = cfg["llm"]
    else:
        provider_cfg = {
            "provider": args.provider,
            "options": {"model": args.model or "gpt-4o-mini", "rate_limit_per_minute": 60},
        }
        # TODO Require the parameters, don't guess them
        # TODO Make rate_limit_per_minute optional

    provider = create_provider("llm", provider_cfg)
    print("Generating...\n")
    output = provider.generate(args.system, args.user)
    print("\nResponse:\n──────────────────────────\n")
    print(output)


if __name__ == "__main__":
    main()
