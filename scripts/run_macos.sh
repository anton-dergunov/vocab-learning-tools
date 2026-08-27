#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
"$project_root/scripts/build_macos.sh"
open "$project_root/build/Acervo.app"
