#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
cd "$project_root"
eval "$("$project_root/scripts/version.sh")"
"$project_root/scripts/build_macos.sh" --release

staging="$project_root/build/macos-release"
rm -rf "$staging"
mkdir -p "$staging"
archive_name="Acervo-$ACERVO_APP_VERSION-$ACERVO_APP_BUILD.zip"
archive="$staging/$archive_name"
ditto -c -k --sequesterRsrc --keepParent "$project_root/build/Acervo.app" "$archive"
checksum=$(shasum -a 256 "$archive" | awk '{ print $1 }')
size=$(wc -c < "$archive" | tr -d ' ')
cat >"$staging/release.json" <<EOF
{
  "version": "$ACERVO_APP_VERSION",
  "build": "$ACERVO_APP_BUILD",
  "file": "$archive_name",
  "size": $size,
  "sha256": "$checksum"
}
EOF
print "Packaged $archive_name ($size bytes)"
