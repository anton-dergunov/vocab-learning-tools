#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence_dir=${ACERVO_EVIDENCE_DIR:-"$repo_root/build/anki-sync-evidence/$timestamp"}
mkdir -p "$evidence_dir"
python_runner=${PYTHON:-python3}
if [ -x "$repo_root/.venv/bin/python" ]; then
  python_runner="$repo_root/.venv/bin/python"
fi

RUN_DOCKER_INTEGRATION_TESTS=true \
ACERVO_EVIDENCE_DIR="$evidence_dir" \
"$python_runner" -m pytest -q -s "$repo_root/tests/integration/test_anki_sync_docker.py"

echo "Validation evidence: $evidence_dir"
