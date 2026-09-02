#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
cd "$project_root"
configuration=Debug
for argument in "$@"; do
  case "$argument" in
    --release) configuration=Release ;;
    *) print -u2 "usage: build_macos.sh [--release]"; exit 2 ;;
  esac
done

# A build step says what stage it is in and what it produced; the tools' own chatter -- asset
# tables, generated plists, replaced signatures -- says neither, so it is kept until it is worth
# reading. On failure everything the step wrote is printed before the script stops.
run_quietly() {
  local label=$1
  shift
  # Not `status`: zsh reserves that name for the last exit code, and assigning it is an error.
  local log step_status=0
  log=$(mktemp "${TMPDIR:-/tmp}/acervo-step.XXXXXX")
  "$@" >"$log" 2>&1 || step_status=$?
  if (( step_status != 0 )); then
    print -u2 "$label failed (exit $step_status):"
    cat "$log" >&2
    rm -f "$log"
    exit $step_status
  fi
  rm -f "$log"
}

eval "$("$project_root/scripts/version.sh")"
if [[ ! -d web/node_modules ]]; then
  print "Installing web dependencies..."
  run_quietly "Installing web dependencies" npm install --prefix web
fi

print "Building the macOS app (this can take a while)..."
run_quietly "Generating app icons" "$project_root/scripts/generate_app_icons.py"
run_quietly "The web build" npm run build:web
run_quietly "Generating the Xcode project" xcodegen generate --spec macos/project.yml
run_quietly "The macOS build" xcodebuild \
  -project macos/Acervo.xcodeproj \
  -scheme Acervo \
  -configuration "$configuration" \
  -derivedDataPath "$project_root/DerivedData" \
  MARKETING_VERSION="$ACERVO_APP_VERSION" \
  CURRENT_PROJECT_VERSION="$ACERVO_APP_BUILD" \
  CODE_SIGNING_ALLOWED=NO \
  build

mkdir -p "$project_root/build"
rm -rf "$project_root/build/Acervo.app"
ditto "$project_root/DerivedData/Build/Products/$configuration/Acervo.app" "$project_root/build/Acervo.app"
run_quietly "Signing the app" \
  codesign --sign - --force --deep --timestamp=none "$project_root/build/Acervo.app"
print "Built $configuration $ACERVO_APP_VERSION ($ACERVO_APP_BUILD) at build/Acervo.app"
