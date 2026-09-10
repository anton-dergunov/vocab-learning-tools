#!/bin/sh
set -eu

PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: run-worker.sh [--root PATH] [--input-archive FILE]" >&2
  echo "         {bootstrap-upload|push|export-state|pull-state|adopt-server}" >&2
  echo "       run-worker.sh [--root PATH] build-dictionary <compiler arguments...>" >&2
  echo "         e.g. build-dictionary --id cc-cedict" >&2
  echo "              build-dictionary --all --language es,en,zh" >&2
  echo "       run-worker.sh [--root PATH] draw-pictures <sweep arguments...>" >&2
  echo "         e.g. draw-pictures sweep --limit 50" >&2
  echo "              draw-pictures plan --language es" >&2
  exit 2
}

acervo_root=
input_archive=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --input-archive) [ "$#" -ge 2 ] || usage; input_archive=$2; shift 2 ;;
    bootstrap-upload|push|export-state|pull-state|adopt-server|build-dictionary|draw-pictures) operation=$1; shift; break ;;
    *) usage ;;
  esac
done
[ "${operation:-}" ] || usage
# The compiler's own flags are passed straight through, so building one dictionary and building
# every Spanish one are the same command with different arguments rather than two wrappers.
if [ "$operation" = build-dictionary ] || [ "$operation" = draw-pictures ]; then
  [ "$#" -ge 1 ] || usage
else
  [ "$#" -eq 0 ] || usage
fi

if [ -z "$acervo_root" ]; then
  if [ -f /etc/acervo-root ]; then
    IFS= read -r acervo_root </etc/acervo-root
  elif [ -d /volume1 ]; then
    acervo_root=/volume1/docker/acervo
  else
    acervo_root=/opt/acervo
  fi
fi
case "$acervo_root" in
  /*/acervo) ;;
  *) echo "Refusing unexpected Acervo root: $acervo_root" >&2; exit 2 ;;
esac

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "Docker Compose is unavailable" >&2
  exit 1
fi

release=$(cat "$acervo_root/current-release")
compose_file="$release/deploy/acervo/compose.yaml"
# `--build` on every run, because a deployment builds only the two long-running services: the worker
# is a `profiles: ["tools"]` container that exists to be `run`, so nothing else ever rebuilds it and
# a job would quietly execute whatever code the last build happened to contain. The layers cache, so
# an unchanged release costs a second.
common_args="-p acervo --env-file $acervo_root/deployment.env --env-file $acervo_root/secrets.env --env-file $acervo_root/llm.env -f $compose_file"

input_dir=
cleanup() {
  status=$?
  trap - EXIT
  if [ -n "$input_dir" ]; then
    case "$input_dir" in "$acervo_root/input/runs/"*) rm -rf -- "$input_dir" ;; esac
  fi
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

case "$operation" in
  bootstrap-upload|push)
    [ -f "$input_archive" ] || { echo "$operation requires an input archive" >&2; exit 2; }
    run_id=$(date -u +%Y%m%dT%H%M%SZ)-$$
    input_dir="$acervo_root/input/runs/$run_id"
    mkdir -p "$input_dir"
    tar -xzf "$input_archive" -C "$input_dir"
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker \
      anki "$operation" "/input/runs/$run_id/manifest.json"
    ;;
  export-state)
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker anki export-state
    ;;
  pull-state)
    # The write half of the same read: `export-state` prints the scheduling, this puts it in the
    # graph where the interface can show it.
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker anki pull-state
    ;;
  adopt-server)
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker \
      anki adopt-server --confirm-no-other-clients
    ;;
  build-dictionary)
    # Compiling streams sources that run to gigabytes, so this is deliberately a command the owner
    # runs rather than something a checkbox triggers.
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker dictionary build "$@"
    ;;
  draw-pictures)
    # The unattended half of sense images. A sweep rather than a watcher: it asks the graph what has
    # no picture, so being run late or twice costs nothing. This is what a cron line calls, and it
    # is one subcommand rather than a new container — the whole reason `acervo-worker` exists.
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker images "$@"
    ;;
esac
