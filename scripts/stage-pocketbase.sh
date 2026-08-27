#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination="$repo_root/deploy/acervo/pocketbase/pb_public"

mkdir -p "$destination"
rsync -a --delete --exclude .gitkeep "$repo_root/web/dist/" "$destination/"
