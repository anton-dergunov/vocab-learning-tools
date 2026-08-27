#!/bin/sh
set -eu

# Synology Container Manager installs Docker outside the restricted sudo PATH.
# These additions are harmless on ordinary Linux hosts.
PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: install.sh [--root PATH] [--archive FILE] [--credentials-stdin | --credentials-file FILE] [--bind-address ADDRESS] [--port PORT] [--reset-data]" >&2
  exit 2
}

acervo_root=
archive=
credentials_stdin=false
credentials_file=
reset_data=false
requested_bind_address=
requested_anki_port=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --archive) [ "$#" -ge 2 ] || usage; archive=$2; shift 2 ;;
    --credentials-stdin) credentials_stdin=true; shift ;;
    --credentials-file) [ "$#" -ge 2 ] || usage; credentials_file=$2; shift 2 ;;
    --bind-address) [ "$#" -ge 2 ] || usage; requested_bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; requested_anki_port=$2; shift 2 ;;
    --reset-data) reset_data=true; shift ;;
    *) usage ;;
  esac
done
[ "$credentials_stdin" = false ] || [ -z "$credentials_file" ] || usage
case "$requested_bind_address" in *[!A-Za-z0-9:._-]*) usage ;; esac
case "$requested_anki_port" in ""|*[!0-9]*) [ -z "$requested_anki_port" ] || usage ;; esac
if [ -n "$requested_anki_port" ] && { [ "$requested_anki_port" -lt 1 ] || [ "$requested_anki_port" -gt 65535 ]; }; then
  usage
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

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "Docker Compose is unavailable; install or update Synology Container Manager" >&2
  exit 1
fi

case "$acervo_root" in
  /*) ;;
  *) echo "Acervo root must be an absolute path" >&2; exit 2 ;;
esac

umask 077
mkdir -p \
  "$acervo_root/data/anki-server" \
  "$acervo_root/data/anki-robot" \
  "$acervo_root/input" \
  "$acervo_root/backups" \
  "$acervo_root/releases"

if [ "$credentials_stdin" = true ] || [ -n "$credentials_file" ]; then
  credentials_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$credentials_tmp"' EXIT HUP INT TERM
  if [ -n "$credentials_file" ]; then
    [ -f "$credentials_file" ] || { echo "Missing credentials file" >&2; exit 2; }
    exec 3<"$credentials_file"
  else
    exec 3<&0
  fi
  IFS= read -r username <&3 || { echo "Missing sync username" >&2; exit 2; }
  IFS= read -r password <&3 || { echo "Missing sync password" >&2; exit 2; }
  exec 3<&-
  case "$username$password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
  username_env=$(printf '%s' "$username" | sed "s/'/\\\\'/g")
  password_env=$(printf '%s' "$password" | sed "s/'/\\\\'/g")
  {
    printf "ACERVO_ANKI_SYNC_USERNAME='%s'\n" "$username_env"
    printf "ACERVO_ANKI_SYNC_PASSWORD='%s'\n" "$password_env"
  } >"$credentials_tmp"
  chmod 600 "$credentials_tmp"
  mv "$credentials_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi

if [ ! -f "$acervo_root/secrets.env" ]; then
  echo "Missing $acervo_root/secrets.env; configure credentials first" >&2
  exit 2
fi
chmod 600 "$acervo_root/secrets.env"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$acervo_root/backups/$timestamp"
mkdir -p "$backup_dir/anki-server" "$backup_dir/anki-robot"
for service in anki-server anki-robot; do
  find "$acervo_root/data/$service" -type f \( \
    -name 'collection*.anki2' -o \
    -name 'collection*.anki21' -o \
    -name 'collection.media' -o \
    -name 'media.db' -o \
    -name '*.db2' \
  \) -exec cp -p {} "$backup_dir/$service/" \;
done

backup_count=$(find "$acervo_root/backups" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
while [ "$backup_count" -gt 10 ]; do
  oldest=$(find "$acervo_root/backups" -mindepth 1 -maxdepth 1 -type d | sort | head -n 1)
  [ -n "$oldest" ] || break
  rm -rf -- "$oldest"
  backup_count=$((backup_count - 1))
done

if [ "$reset_data" = true ]; then
  rm -rf -- "$acervo_root/data/anki-server" "$acervo_root/data/anki-robot"
  mkdir -p "$acervo_root/data/anki-server" "$acervo_root/data/anki-robot"
fi

if [ -n "$archive" ]; then
  release_dir="$acervo_root/releases/$timestamp"
  mkdir -p "$release_dir"
  tar -C "$release_dir" -xzf "$archive"
else
  release_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fi

uid=$(id -u)
gid=$(id -g)
compose_project=${ACERVO_COMPOSE_PROJECT:-acervo}
bind_address=${requested_bind_address:-${ACERVO_BIND_ADDRESS:-127.0.0.1}}
anki_port=${requested_anki_port:-${ACERVO_ANKI_PORT:-27701}}
cat >"$acervo_root/deployment.env" <<EOF
ACERVO_UID=$uid
ACERVO_GID=$gid
ACERVO_BIND_ADDRESS=$bind_address
ACERVO_ANKI_PORT=$anki_port
ACERVO_ANKI_SERVER_DATA=$acervo_root/data/anki-server
ACERVO_ANKI_ROBOT_DATA=$acervo_root/data/anki-robot
ACERVO_INPUT_PATH=$acervo_root/input
EOF
chmod 600 "$acervo_root/deployment.env"

compose_file="$release_dir/deploy/acervo/compose.yaml"
compose -p "$compose_project" \
  --env-file "$acervo_root/deployment.env" \
  --env-file "$acervo_root/secrets.env" \
  -f "$compose_file" up -d --build anki-sync-server

attempt=0
until [ "$(compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" ps --format json anki-sync-server 2>/dev/null | grep -c '"Health":"healthy"' || true)" -gt 0 ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" logs anki-sync-server >&2
    exit 1
  fi
  sleep 2
done

printf '%s\n' "$release_dir" >"$acervo_root/current-release"
echo "Acervo Anki sync server is healthy at $bind_address:$anki_port"
