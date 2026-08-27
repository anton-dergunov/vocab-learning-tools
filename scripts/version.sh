#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -z "${ACERVO_APP_VERSION:-}" ]; then
  ACERVO_APP_VERSION=$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$repo_root/package.json" | head -n 1)
fi
[ -n "$ACERVO_APP_VERSION" ] || { echo "package.json does not declare a version" >&2; exit 1; }

if [ -z "${ACERVO_APP_BUILD:-}" ]; then
  ACERVO_APP_BUILD=$(date -u +%Y%m%d%H%M)
fi

case "${1:-}" in
  --version) printf '%s\n' "$ACERVO_APP_VERSION" ;;
  --build) printf '%s\n' "$ACERVO_APP_BUILD" ;;
  "")
    printf 'ACERVO_APP_VERSION=%s\n' "$ACERVO_APP_VERSION"
    printf 'ACERVO_APP_BUILD=%s\n' "$ACERVO_APP_BUILD"
    printf 'export ACERVO_APP_VERSION ACERVO_APP_BUILD\n'
    ;;
  *) echo "usage: version.sh [--version|--build]" >&2; exit 2 ;;
esac
