#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
cd "$project_root"
eval "$("$project_root/scripts/version.sh")"
[[ -d web/node_modules ]] || npm install --prefix web
"$project_root/scripts/generate_app_icons.py"
npm run build:web
xcodegen generate --spec macos/project.yml
xcodebuild \
  -project macos/Acervo.xcodeproj \
  -scheme Acervo \
  -configuration Debug \
  -derivedDataPath "$project_root/DerivedData" \
  MARKETING_VERSION="$ACERVO_APP_VERSION" \
  CURRENT_PROJECT_VERSION="$ACERVO_APP_BUILD" \
  CODE_SIGNING_ALLOWED=NO \
  test
