#!/bin/sh
# Fetch the pinned spoken-usage-retrieval artifacts into vendor/speech/.
#
# Acervo names one version of the retrieval service in deploy/acervo/speech/pin.json and upgrades
# it deliberately; the two repositories keep their own release cadences
# (docs/features/spoken-clips.md §2.1). This script is what turns that pin into files on disk: the
# wheel the speech image installs and the npm tarball web/ imports.
#
# The digests in the pin are the *release's*, copied from its SHA256SUMS asset. Take them from a
# local build and the wheel will match but the npm tarball will not: hatchling's zip is
# deterministic, while `npm pack` gzips with whatever zlib the building Node version carries, so a
# Node 24 laptop and a Node 22 runner disagree. An artifact already present and matching is left
# alone rather than re-downloaded, so dropping a locally built wheel in here still works for trying
# a version before it is released.
#
#   scripts/fetch_speech.sh              # fetch what is missing, verify what is there
#   scripts/fetch_speech.sh --check      # verify only; never touch the network
#   scripts/fetch_speech.sh --force      # re-fetch even what verifies
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pin="$repo_root/deploy/acervo/speech/pin.json"
destination="$repo_root/vendor/speech"

check_only=false
force=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) check_only=true; shift ;;
    --force) force=true; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -f "$pin" ] || { echo "Missing pin: $pin" >&2; exit 1; }

# python3 rather than jq: the server image, the deployment tests and every developer machine already
# have it, and one more required tool is one more way a fresh clone fails.
read_pin() {
  python3 -c '
import json, sys
pin = json.load(open(sys.argv[1], encoding="utf-8"))
for name, entry in pin["artifacts"].items():
    print(entry["file"], entry["sha256"], sep="\t")
' "$pin"
}

digest() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d" " -f1
  else
    shasum -a 256 "$1" | cut -d" " -f1
  fi
}

field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$pin" "$1"
}

tag=$(field tag)
repository=$(field repository)
version=$(field version)

mkdir -p "$destination"

manifest=$(mktemp)
trap 'rm -f "$manifest"' EXIT HUP INT TERM
read_pin >"$manifest"

# Read from a file rather than a pipe: a `while` on the right of a pipeline runs in a subshell, so
# a failure inside it could not stop the run and every later check would still be attempted.
while IFS="$(printf '\t')" read -r file expected; do
  [ -n "$file" ] || continue
  target="$destination/$file"

  if [ "$force" = false ] && [ -f "$target" ]; then
    actual=$(digest "$target")
    if [ "$actual" = "$expected" ]; then
      echo "ok       $file"
      continue
    fi
    echo "MISMATCH $file" >&2
    echo "         expected $expected" >&2
    echo "         found    $actual" >&2
    echo "         Delete it and re-run, or correct the pin if you meant to change the version." >&2
    exit 1
  fi

  if [ "$check_only" = true ]; then
    echo "MISSING  $file" >&2
    exit 1
  fi

  url="$repository/releases/download/$tag/$file"
  echo "fetch    $file"
  # Into a temporary name first: a half-written artifact that kept the real name would look
  # "already present" on the next run and would then fail verification forever.
  if ! curl --fail --location --silent --show-error --output "$target.part" "$url"; then
    rm -f "$target.part"
    echo "Could not download $url" >&2
    echo "Has $tag been released yet? A locally built artifact placed at $target works too." >&2
    exit 1
  fi

  actual=$(digest "$target.part")
  if [ "$actual" != "$expected" ]; then
    rm -f "$target.part"
    echo "MISMATCH $file after download" >&2
    echo "         expected $expected" >&2
    echo "         found    $actual" >&2
    exit 1
  fi
  mv -- "$target.part" "$target"
  echo "verified $file"
done <"$manifest"

# Anything the pin does not name is a previous version, and leaving it is not merely untidy: the
# speech image does `COPY vendor/speech/*.whl` and then installs the lot, so two wheels of one
# package fail the build outright — and `package_acervo_server.sh` would have carried both into the
# release archive first. Only ever the pinned pair is on disk.
#
# Not under --check, which promises to verify and change nothing. A stale artifact is not a
# verification failure either: what the pin names is present and correct, which is the question
# --check asks.
if [ "$check_only" = false ]; then
for stale in "$destination"/*; do
  [ -e "$stale" ] || continue
  name=${stale##*/}
  if ! cut -f1 <"$manifest" | grep -qxF "$name"; then
    echo "remove   $name"
    rm -f -- "$stale"
  fi
done
fi

echo "Pinned spoken-usage-retrieval $version is in vendor/speech/"
