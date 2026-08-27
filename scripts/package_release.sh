#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
eval "$("$repo_root/scripts/version.sh")"
export ACERVO_APP_VERSION ACERVO_APP_BUILD

if [ "$(uname -s)" = Darwin ]; then
  "$repo_root/scripts/package_macos_release.sh"
  ACERVO_INCLUDE_MACOS_RELEASE=true
else
  ACERVO_INCLUDE_MACOS_RELEASE=false
fi
export ACERVO_INCLUDE_MACOS_RELEASE

npm run stage:pwa
"$repo_root/scripts/package_acervo_server.sh"
