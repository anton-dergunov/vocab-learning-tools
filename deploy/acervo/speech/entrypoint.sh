#!/bin/sh
# Seed the channel catalogue, then hand over to whatever was asked for.
#
# `channels seed` copies the catalogues that travel inside the wheel into the mounted catalogue
# directory and never overwrites one that is already there, so this is safe on every start: a
# channel the owner added survives, and a language a later version introduced is picked up.
#
# It is not optional. An empty catalogue directory cannot be filled through the API — the channel
# repository only rewrites a `<language>.json` that already exists, and the catalogue schema
# rejects one with no sections — so without this a fresh deployment would offer channel management
# with nothing to manage.
set -eu

if [ -n "${SPEECH_RETRIEVAL_CATALOGUE_DIR:-}" ]; then
  speech-retrieval channels seed --into "$SPEECH_RETRIEVAL_CATALOGUE_DIR" >/dev/null
fi

exec "$@"
