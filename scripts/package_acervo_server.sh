#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_root/build"
archive="$output_dir/acervo-server.tar.gz"
temporary=$(mktemp -d "${TMPDIR:-/tmp}/acervo-server-package.XXXXXX")
bundle="$temporary/release"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM

if [ ! -f "$repo_root/deploy/acervo/pocketbase/pb_public/manifest.webmanifest" ]; then
  echo "Staged Acervo PWA is missing. Run npm run stage:pwa first." >&2
  exit 1
fi

eval "$("$repo_root/scripts/version.sh")"
mkdir -p "$output_dir" "$bundle"
for directory in deploy docs requirements scripts src templates; do
  mkdir -p "$bundle/$directory"
  rsync -a --exclude .DS_Store --exclude __pycache__ --exclude '*.pyc' \
    "$repo_root/$directory/" "$bundle/$directory/"
done
cp "$repo_root/package.json" "$bundle/package.json"

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

archive_entries="deploy docs requirements scripts src templates package.json version.json"
[ ! -d "$bundle/downloads" ] || archive_entries="$archive_entries downloads"

if [ "$(uname -s)" = Darwin ]; then
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C "$bundle" -czf "$archive" \
    $archive_entries
else
  tar -C "$bundle" -czf "$archive" $archive_entries
fi

printf '%s\n' "$archive"
