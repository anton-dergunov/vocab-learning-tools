#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Where the archive lands. Overridable, and the reason is a deployment that failed for it: the path
# used to be fixed at `build/acervo-server.tar.gz`, so the deployment tests rewrote the very file a
# concurrent `./deploy.sh` was streaming. The remote saw a valid gzip stream with another process's
# bytes appended, reported "trailing garbage" and a tar child status 2, and gave up with "the
# release archive has no Acervo installer" — a failure with nothing in it pointing at the cause.
# Tests pass a path of their own; a real deploy keeps the default.
archive=${ACERVO_PACKAGE_ARCHIVE:-"$repo_root/build/acervo-server.tar.gz"}
output_dir=$(dirname -- "$archive")
temporary=$(mktemp -d "${TMPDIR:-/tmp}/acervo-server-package.XXXXXX")
bundle="$temporary/release"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM

if [ ! -f "$repo_root/deploy/acervo/server/web/manifest.webmanifest" ]; then
  echo "Staged Acervo PWA is missing. Run npm run stage:pwa first." >&2
  exit 1
fi

eval "$("$repo_root/scripts/version.sh")"
mkdir -p "$output_dir" "$bundle"
for directory in config deploy dictionaries docs models prompts requirements scripts src templates; do
  mkdir -p "$bundle/$directory"
  rsync -a --exclude .DS_Store --exclude __pycache__ --exclude '*.pyc' --exclude 'llm.env' \
    "$repo_root/$directory/" "$bundle/$directory/"
done
# The server image installs the package from the bundle, so its build files travel too.
cp "$repo_root/package.json" "$repo_root/pyproject.toml" "$repo_root/README.md" "$bundle/"

cat >"$bundle/version.json" <<EOF
{ "version": "$ACERVO_APP_VERSION", "build": "$ACERVO_APP_BUILD" }
EOF

if [ "${ACERVO_INCLUDE_MACOS_RELEASE:-false}" = true ] && [ -f "$repo_root/build/macos-release/release.json" ]; then
  release_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$repo_root/build/macos-release/release.json" | head -n 1)
  release_build=$(sed -n 's/.*"build"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$repo_root/build/macos-release/release.json" | head -n 1)
  if [ "$release_version" != "$ACERVO_APP_VERSION" ] || [ "$release_build" != "$ACERVO_APP_BUILD" ]; then
    echo "The macOS release does not match the server version/build; package the coordinated release again" >&2
    exit 1
  fi
  mkdir -p "$bundle/downloads"
  cp -R "$repo_root/build/macos-release/." "$bundle/downloads/"
fi

# Compiled dictionaries are built on the machine that runs the compiler and are not in the
# repository, so they travel in the release the way the macOS application does. This is a private
# copy moving between the owner's own machines; the licensing rule in docs §9 is about publishing to
# the world and does not apply.
dictionary_artifacts=${ACERVO_DICTIONARY_ARTIFACTS:-"$repo_root/data/dictionaries/out"}
if [ "${ACERVO_INCLUDE_DICTIONARIES:-true}" = true ] && [ -d "$dictionary_artifacts" ] \
   && [ -n "$(find "$dictionary_artifacts" -maxdepth 1 -name '*.json' -print -quit)" ]; then
  mkdir -p "$bundle/dictionary-artifacts"
  # Only complete triples: a `.json` with no payload beside it would be listed by the server and
  # then fail at the moment someone tried to store it.
  for metadata in "$dictionary_artifacts"/*.json; do
    id=$(basename "$metadata" .json)
    if [ -f "$dictionary_artifacts/$id.dict" ] && [ -f "$dictionary_artifacts/$id.idx" ]; then
      cp "$metadata" "$dictionary_artifacts/$id.dict" "$dictionary_artifacts/$id.idx" \
        "$bundle/dictionary-artifacts/"
    else
      echo "Skipping incomplete dictionary $id (no .dict/.idx beside its metadata)" >&2
    fi
  done
  bundled=$(find "$bundle/dictionary-artifacts" -name '*.json' | wc -l | tr -d ' ')
  size=$(du -sh "$bundle/dictionary-artifacts" | cut -f1)
  # stderr, not stdout: this script's stdout is the archive path and deploy.sh reads it.
  echo "Bundling $bundled compiled dictionaries ($size). Set ACERVO_INCLUDE_DICTIONARIES=false to skip." >&2
fi

archive_entries="config deploy dictionaries docs models prompts requirements scripts src templates package.json pyproject.toml README.md version.json"
[ ! -d "$bundle/downloads" ] || archive_entries="$archive_entries downloads"
[ ! -d "$bundle/dictionary-artifacts" ] || archive_entries="$archive_entries dictionary-artifacts"

if [ "$(uname -s)" = Darwin ]; then
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C "$bundle" -czf "$archive" \
    $archive_entries
else
  tar -C "$bundle" -czf "$archive" $archive_entries
fi

printf '%s\n' "$archive"
