#!/bin/sh
set -eu

PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: run-worker.sh [--root PATH] [--input-archive FILE]" >&2
  echo "         {bootstrap-upload|push|export-state|adopt-server|build-dictionary} [ID]" >&2
  exit 2
}

acervo_root=
input_archive=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --input-archive) [ "$#" -ge 2 ] || usage; input_archive=$2; shift 2 ;;
    bootstrap-upload|push|export-state|adopt-server|build-dictionary) operation=$1; shift; break ;;
    *) usage ;;
  esac
done
[ "${operation:-}" ] || usage
if [ "$operation" = build-dictionary ]; then
  [ "$#" -eq 1 ] || usage
  dictionary_id=$1
  shift
fi
[ "$#" -eq 0 ] || usage

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
common_args="-p acervo --env-file $acervo_root/deployment.env --env-file $acervo_root/secrets.env -f $compose_file"

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
    compose $common_args --profile tools run --rm acervo-worker \
      anki "$operation" "/input/runs/$run_id/manifest.json"
    ;;
  export-state)
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm acervo-worker anki export-state
    ;;
  adopt-server)
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm acervo-worker \
      anki adopt-server --confirm-no-other-clients
    ;;
  build-dictionary)
    # Compiling streams a source that can be over a gigabyte, so this is deliberately a command the
    # owner runs rather than something a checkbox triggers.
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm acervo-worker \
      dictionary build --id "$dictionary_id"
    ;;
esac
