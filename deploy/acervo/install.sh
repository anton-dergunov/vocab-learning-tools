#!/bin/sh
set -eu

# Synology Container Manager installs Docker outside the restricted sudo PATH.
# These additions are harmless on ordinary Linux hosts.
PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: install.sh [--root PATH] [--archive FILE] [--credentials-stdin | --credentials-file FILE] [--bind-address ADDRESS] [--port PORT] [--app-bind-address ADDRESS] [--app-port PORT] [--reset-data] [--reset-pocketbase]" >&2
  exit 2
}

# A step says what stage it is in and what it produced; a container runtime's layer-by-layer
# progress says neither, so it is kept until it is worth reading. On failure everything the step
# wrote is printed before the script stops. Deliberately not a pipeline: this is POSIX sh, where
# pipefail does not exist and a pipe would discard the step's own exit status.
run_quietly() {
  quiet_label=$1
  shift
  quiet_log=$(mktemp "${TMPDIR:-/tmp}/acervo-step.XXXXXX")
  quiet_status=0
  "$@" >"$quiet_log" 2>&1 || quiet_status=$?
  if [ "$quiet_status" -ne 0 ]; then
    echo "$quiet_label failed (exit $quiet_status):" >&2
    cat "$quiet_log" >&2
    rm -f "$quiet_log"
    exit "$quiet_status"
  fi
  rm -f "$quiet_log"
}

acervo_root=
archive=
credentials_stdin=false
credentials_file=
reset_data=false
reset_pocketbase=false
requested_bind_address=
requested_anki_port=
requested_app_bind_address=
requested_app_port=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --archive) [ "$#" -ge 2 ] || usage; archive=$2; shift 2 ;;
    --credentials-stdin) credentials_stdin=true; shift ;;
    --credentials-file) [ "$#" -ge 2 ] || usage; credentials_file=$2; shift 2 ;;
    --bind-address) [ "$#" -ge 2 ] || usage; requested_bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; requested_anki_port=$2; shift 2 ;;
    --app-bind-address) [ "$#" -ge 2 ] || usage; requested_app_bind_address=$2; shift 2 ;;
    --app-port) [ "$#" -ge 2 ] || usage; requested_app_port=$2; shift 2 ;;
    --reset-data) reset_data=true; shift ;;
    --reset-pocketbase) reset_pocketbase=true; shift ;;
    *) usage ;;
  esac
done
[ "$credentials_stdin" = false ] || [ -z "$credentials_file" ] || usage
case "$requested_bind_address" in *[!A-Za-z0-9:._-]*) usage ;; esac
case "$requested_app_bind_address" in *[!A-Za-z0-9:._-]*) usage ;; esac
case "$requested_anki_port" in ""|*[!0-9]*) [ -z "$requested_anki_port" ] || usage ;; esac
case "$requested_app_port" in ""|*[!0-9]*) [ -z "$requested_app_port" ] || usage ;; esac
if [ -n "$requested_anki_port" ] && { [ "$requested_anki_port" -lt 1 ] || [ "$requested_anki_port" -gt 65535 ]; }; then
  usage
fi
if [ -n "$requested_app_port" ] && { [ "$requested_app_port" -lt 1 ] || [ "$requested_app_port" -gt 65535 ]; }; then
  usage
fi
effective_anki_port=${requested_anki_port:-${ACERVO_ANKI_PORT:-27701}}
effective_app_port=${requested_app_port:-${ACERVO_APP_PORT:-27702}}
[ "$effective_anki_port" != "$effective_app_port" ] || {
  echo "The Acervo app/PocketBase port must differ from the Anki sync port" >&2
  exit 2
}

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
  "$acervo_root/data/acervo-worker" \
  "$acervo_root/data/pocketbase" \
  "$acervo_root/data/dictionaries" \
  "$acervo_root/downloads" \
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
  IFS= read -r pb_email <&3 || { echo "Missing PocketBase superuser email" >&2; exit 2; }
  IFS= read -r pb_password <&3 || { echo "Missing PocketBase superuser password" >&2; exit 2; }
  # Optional, so end-of-input here is not an error: a server without a key serves everything except
  # capture, and says so.
  IFS= read -r gemini_api_key <&3 || gemini_api_key=""
  exec 3<&-
  case "$username$password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
  username_env=$(printf '%s' "$username" | sed "s/'/\\\\'/g")
  password_env=$(printf '%s' "$password" | sed "s/'/\\\\'/g")
  pb_email_env=$(printf '%s' "$pb_email" | sed "s/'/\\\\'/g")
  pb_password_env=$(printf '%s' "$pb_password" | sed "s/'/\\\\'/g")
  gemini_api_key_env=$(printf '%s' "$gemini_api_key" | sed "s/'/\\\\'/g")
  {
    printf "ACERVO_ANKI_SYNC_USERNAME='%s'\n" "$username_env"
    printf "ACERVO_ANKI_SYNC_PASSWORD='%s'\n" "$password_env"
    printf "ACERVO_PB_SUPERUSER_EMAIL='%s'\n" "$pb_email_env"
    printf "ACERVO_PB_SUPERUSER_PASSWORD='%s'\n" "$pb_password_env"
    printf "GEMINI_API_KEY='%s'\n" "$gemini_api_key_env"
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
. "$acervo_root/secrets.env"
: "${ACERVO_PB_SUPERUSER_EMAIL:?Set ACERVO_PB_SUPERUSER_EMAIL in $acervo_root/secrets.env}"
: "${ACERVO_PB_SUPERUSER_PASSWORD:?Set ACERVO_PB_SUPERUSER_PASSWORD in $acervo_root/secrets.env}"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="$acervo_root/backups/$timestamp"
mkdir -p "$backup_dir/anki-server" "$backup_dir/acervo-worker"
for service in anki-server acervo-worker; do
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
  rm -rf -- "$acervo_root/data/anki-server" "$acervo_root/data/acervo-worker"
  mkdir -p "$acervo_root/data/anki-server" "$acervo_root/data/acervo-worker"
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
app_bind_address=${requested_app_bind_address:-${ACERVO_APP_BIND_ADDRESS:-127.0.0.1}}
app_port=${requested_app_port:-${ACERVO_APP_PORT:-27702}}
app_version=0.0.0
app_build=0
if [ -f "$release_dir/version.json" ]; then
  app_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$release_dir/version.json" | head -n 1)
  app_build=$(sed -n 's/.*"build"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$release_dir/version.json" | head -n 1)
fi
cat >"$acervo_root/deployment.env" <<EOF
ACERVO_UID=$uid
ACERVO_GID=$gid
ACERVO_BIND_ADDRESS=$bind_address
ACERVO_ANKI_PORT=$anki_port
ACERVO_APP_BIND_ADDRESS=$app_bind_address
ACERVO_APP_PORT=$app_port
ACERVO_APP_VERSION=$app_version
ACERVO_APP_BUILD=$app_build
ACERVO_ANKI_SERVER_DATA=$acervo_root/data/anki-server
ACERVO_WORKER_DATA=$acervo_root/data/acervo-worker
ACERVO_DICTIONARIES=$acervo_root/data/dictionaries
ACERVO_PB_DATA=$acervo_root/data/pocketbase
ACERVO_DOWNLOADS=$acervo_root/downloads
ACERVO_INPUT_PATH=$acervo_root/input
EOF
chmod 600 "$acervo_root/deployment.env"

# A build made on macOS publishes the matching native application. A build made elsewhere keeps
# the last known-good archive available instead of silently withdrawing desktop updates.
if [ -f "$release_dir/downloads/release.json" ]; then
  find "$acervo_root/downloads" -maxdepth 1 -type f -name '*.zip' -delete
  cp -R "$release_dir/downloads/." "$acervo_root/downloads/"
elif [ -f "$acervo_root/downloads/release.json" ]; then
  echo "This release carries no macOS application; keeping the previously published one"
fi

# Compiled dictionaries built on the operator's machine. Merged rather than replaced: building only
# the Spanish ones and deploying must not withdraw the Chinese ones deployed last week. Removing one
# is deleting its three files from this directory.
if [ -d "$release_dir/dictionary-artifacts" ]; then
  cp -R "$release_dir/dictionary-artifacts/." "$acervo_root/data/dictionaries/"
  installed_dictionaries=$(find "$acervo_root/data/dictionaries" -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')
  echo "Published $installed_dictionaries compiled dictionaries"
fi

compose_file="$release_dir/deploy/acervo/compose.yaml"

# A schema change is deployed by rewriting the bootstrap migration, and PocketBase records applied
# migrations by filename — so an existing database never picks the rewrite up. Rebuilding the
# database is therefore the supported upgrade path (AGENTS.md), and this is it. Anki review history
# lives under --reset-data instead: it is irreplaceable, and a schema rebuild must not take it out.
if [ "$reset_pocketbase" = true ]; then
  echo "Stopping PocketBase to replace its database..."
  compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    -f "$compose_file" stop pocketbase >/dev/null 2>&1 || true
  # Copied only once the container is stopped: copying a live WAL database is the classic route to
  # a backup that looks fine until the day you need it.
  if [ -d "$acervo_root/data/pocketbase" ]; then
    mkdir -p "$backup_dir/pocketbase"
    cp -R "$acervo_root/data/pocketbase/." "$backup_dir/pocketbase/" 2>/dev/null || true
  fi
  rm -rf -- "$acervo_root/data/pocketbase"
  mkdir -p "$acervo_root/data/pocketbase"
  echo "PocketBase database replaced; the previous one is in $backup_dir/pocketbase"
fi

echo "Building and starting containers..."
run_quietly "Building and starting containers" compose -p "$compose_project" \
  --env-file "$acervo_root/deployment.env" \
  --env-file "$acervo_root/secrets.env" \
  -f "$compose_file" up -d --build anki-sync-server pocketbase

echo "Waiting for anki-sync-server to become healthy..."
attempt=0
until [ "$(compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" ps --format json anki-sync-server 2>/dev/null | grep -c '"Health":"healthy"' || true)" -gt 0 ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" logs anki-sync-server >&2
    exit 1
  fi
  sleep 2
done

echo "Waiting for pocketbase to become healthy..."
attempt=0
until [ "$(compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" ps --format json pocketbase 2>/dev/null | grep -c '"Health":"healthy"' || true)" -gt 0 ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" logs pocketbase >&2
    exit 1
  fi
  sleep 2
done

# Quiet on purpose: PocketBase confirms the upsert by echoing the account's address, and the
# summary below already says the server is up.
run_quietly "Configuring the PocketBase superuser" \
  compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" -f "$compose_file" \
  exec -T pocketbase /pb/pocketbase superuser upsert "$ACERVO_PB_SUPERUSER_EMAIL" "$ACERVO_PB_SUPERUSER_PASSWORD"

printf '%s\n' "$release_dir" >"$acervo_root/current-release"
echo "Acervo Anki sync server is healthy at $bind_address:$anki_port"
echo "Acervo internal HTTP backend is healthy at http://$app_bind_address:$app_port"
echo "Open the separately configured HTTPS reverse-proxy or Tailscale Serve address; this deployment does not claim the host's default HTTPS endpoint."
