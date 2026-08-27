#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_root/build"
archive="$output_dir/acervo-server.tar.gz"

mkdir -p "$output_dir"
tar -C "$repo_root" -czf "$archive" \
  deploy/acervo \
  docs/acervo-anki-sync.md \
  requirements/anki-sync.txt \
  requirements/core.txt \
  scripts/anki_robot.py \
  scripts/integration/anki_sync_client.py \
  src/vocabgen \
  templates

printf '%s\n' "$archive"
