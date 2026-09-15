#!/usr/bin/env python3
"""Step 5: tap → meaning, through Acervo's own model layer, one (provider, model) pair at a time.

Runs in the *application* environment (the repository's .venv), not the spike's: it calls
`acervo.services.models.llm_json`, so a result here is what the server would get. The sentence it
sends is what OCR produced for the tap, taken from a `taps` result file, so OCR damage is part of
the test rather than cleaned away beforehand.

    set -a; . ./.env; set +a
    .venv/bin/python research/photo_capture/quick.py --taps research/photo_capture/runs/taps.json \
        --pair gemini-free:gemini/gemini-3.1-flash-lite --pair cloudflare
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from acervo.errors import ApiError
from acervo.services import models as model_service
from acervo.settings import Settings

HERE = Path(__file__).resolve().parent
PROMPT = (HERE / "quick_prompt.md").read_text()


def marked(sentence: str, start: int, end: int) -> str:
    return sentence[:start] + "*" + sentence[start:end] + "*" + sentence[end:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taps", type=Path, required=True)
    parser.add_argument("--pair", action="append", required=True,
                        help="provider id, or provider:model to pin one model")
    parser.add_argument("--gloss-language", default="English")
    parser.add_argument("--out", type=Path, default=HERE / "runs" / "quick.json")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--pace", type=float, default=0.0,
                        help="seconds between calls: the Gemini free tier allows 15 a minute per model")
    args = parser.parse_args()

    settings = Settings()
    taps = json.loads(args.taps.read_text())
    out = json.loads(args.out.read_text()) if args.out.exists() else {}
    system = PROMPT.replace("{gloss_language}", args.gloss_language)

    for pair in args.pair:
        choice = tuple(pair.split(":", 1)) if ":" in pair else pair
        # Pin exactly this pair, through the same chain code llm_json always walks.
        model_service.chain_for = lambda _s, _o, _k="text", c=choice: [c]
        for tap in taps:
            key = f"{pair}|{tap['id']}"
            if key in out and out[key]["error"] is None and len(out[key]["latency"]) >= args.repeat:
                continue
            user = (f"Languages this learner studies: es\n\n"
                    f"Sentence (from OCR):\n{marked(tap['ocrSentence'], tap['wordStart'], tap['wordEnd'])}")
            latencies, answer, model, error = [], None, None, None
            for _ in range(args.repeat):
                started = time.perf_counter()
                try:
                    answer, called = model_service.llm_json(settings, None, system, user, caller="photo-quick")
                    model = called.model
                except ApiError as refused:
                    error = f"{refused.code}: {refused.message}"
                latencies.append(round(time.perf_counter() - started, 3))
                time.sleep(args.pace)
            out[key] = {"pair": pair, "tap": tap["id"], "answer": answer, "model": model,
                        "error": error, "latency": latencies}
            print(f"{pair:45} {tap['id']:28} {latencies[-1]:5.2f}s "
                  f"{(answer or {}).get('lemma')!r} ← truth {tap['unit']!r}", flush=True)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
