#!/bin/sh
set -eu

# The built interface is `.dockerignore`d, so this is what puts it where a build context can see it.
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination="$repo_root/deploy/acervo/server/web"

mkdir -p "$destination"
rsync -a --delete --exclude .gitkeep "$repo_root/web/dist/" "$destination/"
