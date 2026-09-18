#!/bin/sh
# The unattended half: finish the arms, judge, score, report, and build the review page.
#
# Every stage is idempotent — run.py and judge.py both skip work already on disk — so this can be
# re-run after an interruption and will only do what is missing. Run it under `caffeinate -is`, or
# the laptop sleeps an hour in.
#
#   caffeinate -is ./experiments/compose-lesson-line/overnight.sh <runId>
set -eu

run_id="${1:?usage: overnight.sh <runId>}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
here="$root/experiments/compose-lesson-line"
run_dir="$here/runs/$run_id"
export PYTHONPATH="$here"
python="$root/.venv/bin/python"

[ -d "$run_dir" ] || { echo "no such run: $run_dir" >&2; exit 1; }
: "${ACERVO_VERTEX_PROJECT:?set ACERVO_VERTEX_PROJECT}"

say() { printf '\n=== %s · %s\n' "$(date +%H:%M:%S)" "$1"; }

say "the metric, before anything else"
"$python" "$here/score.py" --selftest

say "dropping any stored retryable failure, so the fill pass can reach those cells"
"$python" - "$run_dir" <<'PRUNE'
import json, sys
from pathlib import Path

RETRYABLE = ("rate_limited", "unavailable", "unreachable")
# A refusal for quota is not an answer, and a file is how this runner remembers it already asked.
# Left in place it would be mistaken for work done and that cell would never be filled.
dropped = 0
for path in Path(sys.argv[1]).rglob("*.json"):
    if path.name == "manifest.json" or path.parent.parent.name == "judged":
        continue
    record = json.loads(path.read_text(encoding="utf-8"))
    if "wordId" in record and not record.get("ok") and record.get("reason") in RETRYABLE:
        path.unlink()
        dropped += 1
print(f"{dropped} retryable failure(s) dropped")
PRUNE

say "the arms (skips what is already on disk)"
"$python" "$here/run.py" --repeats 3 --max-cost-usd 2.00 --run "$run_id" \
  --pair gemini-free:gemini/gemini-3.5-flash-lite \
  --pair vertex:vertex_ai/gemini-3.8-flash \
  --pair cloudflare

say "scoring"
"$python" "$here/score.py" "$run_dir"

say "the judge"
"$python" "$here/judge.py" "$run_dir" --concurrency 2 --max-cost-usd 5.00

say "a second judging pass, for anything that was rate limited"
"$python" "$here/judge.py" "$run_dir" --concurrency 1 --max-cost-usd 5.00

say "the tables"
{
  "$python" "$here/report.py" "$run_dir"
  "$python" "$here/report.py" "$run_dir" --fields
} > "$run_dir/report.md"
cat "$run_dir/report.md"

say "the review page"
"$python" "$here/review.py" build "$run_dir"

printf '\nIn the morning:\n  cd %s/review && python3 -m http.server 8765\n' "$run_dir"
printf '  then: %s %s/review.py score %s\n' "$python" "$here" "$run_dir"
