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
# `ACERVO_LEXIBEAT_BUNDLE` is unset, compose falls back to a *named volume*, and 3 GB unpacks,
# verifies and reports success into a store this container does not mount. Printing that command
# here is how this deployment lost a bundle once; `--install-samples` is the one that cannot.
set -eu

# Not when the command being wrapped is the bundle tool itself. `lexibeat-bundle fetch` runs in a
# container of its own, so this speaks *before* the fetch it is about to perform — telling the owner
# to install the samples in the middle of them installing the samples. Whoever ran it knows.
case "${1:-}" in
  lexibeat-bundle) exec "$@" ;;
esac

# The package resolves its default bundle relative to the repository root, which in a wheel install
# is `site-packages`, so it must be told. Where is read from the pin the image was built with: the
# bundle it names, and no other, so a volume still holding an older one reads as no bundle rather
# than quietly rendering the music the pinned one replaced. It is exported before the package is
# imported, which is when it reads it.
if [ -z "${LEXIBEAT_BUNDLE_ROOT:-}" ]; then
  LEXIBEAT_BUNDLE_ROOT=/var/lib/lexibeat/bundle/$(python -c \
    'import json; print(json.load(open("/app/pin.json"))["bundle"]["root"])')
  export LEXIBEAT_BUNDLE_ROOT
fi

# Complete, and not merely a readable catalogue: a render drops any bed whose sample is missing
# rather than failing, so a half-unpacked bundle makes thinner music without a word said. Advisory:
# a manifest it cannot read is said here, never a reason not to start — the service still serves.
verdict=$(python -c 'from lexibeat.bundle import status; s = status()
print("complete" if s["complete"] else "partial" if s["present"] else "absent",
      s["version"] or "-", s["assets"], "files,", s["missing"], "missing")' 2>/dev/null) \
  || verdict="unreadable"
case "$verdict" in
  complete*)
    echo "lexibeat: sample bundle v$(echo "$verdict" | cut -d' ' -f2) at $LEXIBEAT_BUNDLE_ROOT" >&2 ;;
  *)
    echo "lexibeat: NO complete sample bundle at $LEXIBEAT_BUNDLE_ROOT ($verdict) — loops cannot" \
         "be made. Install it once, from the machine you deploy with:" >&2
    echo "lexibeat:   ./deploy.sh --install-samples" >&2 ;;
esac

exec "$@"
