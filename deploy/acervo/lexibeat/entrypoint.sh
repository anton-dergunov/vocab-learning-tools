#!/bin/sh
# Say whether the sample bundle is there, then hand over to whatever was asked for.
#
# One line, and it earns its place. Without the bundle the engine still serves — that is deliberate,
# and why the healthcheck asserts liveness rather than readiness — but it can then offer only the
# sample-free `electronic` palette, which is not a slightly plainer version of the same thing. It is
# the difference between recorded instruments and oscillators. That state has to be visible in the
# log rather than only to whoever thinks to read /api/v1/schema.
set -eu

if [ -n "${LEXIBEAT_BUNDLE_ROOT:-}" ] && [ -f "$LEXIBEAT_BUNDLE_ROOT/catalog.sqlite3" ]; then
  echo "lexibeat: sample bundle at $LEXIBEAT_BUNDLE_ROOT" >&2
else
  echo "lexibeat: NO sample bundle at ${LEXIBEAT_BUNDLE_ROOT:-<unset>} — loops will use the" \
       "sample-free electronic palette. Fetch it once with:" >&2
  echo "lexibeat:   docker compose run --rm lexibeat lexibeat-bundle fetch --into /var/lib/lexibeat/bundle --from <release url> --sha256 <digest>" >&2
fi

exec "$@"
