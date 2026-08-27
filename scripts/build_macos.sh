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

eval "$("$project_root/scripts/version.sh")"
[[ -d web/node_modules ]] || npm install --prefix web
"$project_root/scripts/generate_app_icons.py"
npm run build:web
xcodegen generate --spec macos/project.yml
xcodebuild \
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
codesign --sign - --force --deep --timestamp=none "$project_root/build/Acervo.app"
print "Built $configuration $ACERVO_APP_VERSION ($ACERVO_APP_BUILD) at build/Acervo.app"
