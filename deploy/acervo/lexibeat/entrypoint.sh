#!/bin/sh
# Say whether the sample bundle is there, then hand over to whatever was asked for.
#
# One line, and it earns its place. Without the bundle the engine still *serves* — that is deliberate,
# and why the healthcheck asserts liveness rather than readiness — but it cannot render: fifteen of
# its sixteen bed families name instruments loaded from the catalogue, so a render dies partway
# through on a missing sample. That state has to be visible in the log rather than only to whoever
# thinks to read /api/v1/schema.
#
# **And the command below is not the obvious one, deliberately.** A bare
# `docker compose -f compose.yaml run --rm lexibeat …` omits the deployment's env file, so
# `ACERVO_LEXIBEAT_BUNDLE` is unset, compose falls back to a *named volume*, and 1.9 GB unpacks,
# verifies and reports success into a store this container does not mount. Printing that command
# here is how this deployment lost a bundle once; `--install-samples` is the one that cannot.
set -eu

# Not when the command being wrapped is the bundle tool itself. `lexibeat-bundle fetch` runs in a
# container of its own, so this speaks *before* the fetch it is about to perform — telling the owner
# to install the samples in the middle of them installing the samples. Whoever ran it knows.
case "${1:-}" in
  lexibeat-bundle) exec "$@" ;;
esac

if [ -n "${LEXIBEAT_BUNDLE_ROOT:-}" ] && [ -f "$LEXIBEAT_BUNDLE_ROOT/catalog.sqlite3" ]; then
  echo "lexibeat: sample bundle at $LEXIBEAT_BUNDLE_ROOT" >&2
else
  echo "lexibeat: NO sample bundle at ${LEXIBEAT_BUNDLE_ROOT:-<unset>} — loops cannot be made." \
       "Install it once, from the machine you deploy with:" >&2
  echo "lexibeat:   ./deploy.sh --install-samples" >&2
fi

exec "$@"
