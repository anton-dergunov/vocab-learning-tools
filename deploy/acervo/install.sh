#!/bin/sh
set -eu

# Synology Container Manager installs Docker outside the restricted sudo PATH.
# These additions are harmless on ordinary Linux hosts.
PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: install.sh [--root PATH] [--archive FILE] [--credentials-stdin | --credentials-file FILE] [--llm-credentials-file FILE] [--bind-address ADDRESS] [--port PORT] [--app-bind-address ADDRESS] [--app-port PORT] [--reset-data] [--reset-database]" >&2
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
llm_credentials_file=
reset_data=false
reset_database=false
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
    --llm-credentials-file) [ "$#" -ge 2 ] || usage; llm_credentials_file=$2; shift 2 ;;
    --bind-address) [ "$#" -ge 2 ] || usage; requested_bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; requested_anki_port=$2; shift 2 ;;
    --app-bind-address) [ "$#" -ge 2 ] || usage; requested_app_bind_address=$2; shift 2 ;;
    --app-port) [ "$#" -ge 2 ] || usage; requested_app_port=$2; shift 2 ;;
    --reset-data) reset_data=true; shift ;;
    --reset-database) reset_database=true; shift ;;
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
  echo "The Acervo app port must differ from the Anki sync port" >&2
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
  "$acervo_root/data/server" \
  "$acervo_root/data/dictionaries" \
  "$acervo_root/data/media" \
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
  exec 3<&-
  case "$username$password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
  username_env=$(printf '%s' "$username" | sed "s/'/\\\\'/g")
  password_env=$(printf '%s' "$password" | sed "s/'/\\\\'/g")
  {
    printf "ACERVO_ANKI_SYNC_USERNAME='%s'\n" "$username_env"
    printf "ACERVO_ANKI_SYNC_PASSWORD='%s'\n" "$password_env"
    # Everything this block does not own is carried over. Rewriting the file wholesale would take
    # the token signing secret with it, and the next block would mint a fresh one — which signs out
    # every device on the tailnet because someone reconfigured the Anki password.
    if [ -f "$acervo_root/secrets.env" ]; then
      grep -v '^ACERVO_ANKI_SYNC_USERNAME=\|^ACERVO_ANKI_SYNC_PASSWORD=' \
        "$acervo_root/secrets.env" || true
    fi
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

# There is no superuser any more: the server has one kind of account, and `admin.py accounts create`
# is the only thing that makes one. An already-deployed secrets.env still carries the pair, so move
# it out once rather than leaving two dead variables behind. This erases itself.
if grep -q '^ACERVO_PB_SUPERUSER_' "$acervo_root/secrets.env"; then
  secrets_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$secrets_tmp"' EXIT HUP INT TERM
  # `|| true` because grep reports "no lines matched" as a failure, and set -e would take it.
  grep -v '^ACERVO_PB_SUPERUSER_' "$acervo_root/secrets.env" >"$secrets_tmp" || true
  chmod 600 "$secrets_tmp"
  mv "$secrets_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi

# The token signing secret. Minted once and kept, because regenerating it signs out every device.
if ! grep -q '^ACERVO_JWT_SECRET=' "$acervo_root/secrets.env"; then
  printf "ACERVO_JWT_SECRET='%s'\n" "$(head -c 48 /dev/urandom | base64 | tr -d '=+/\n')" \
    >>"$acervo_root/secrets.env"
fi
chmod 600 "$acervo_root/secrets.env"
. "$acervo_root/secrets.env"

# Provider credentials are deliberately independent of the server and Anki credentials. Switching
# between paid Vertex ingestion and a Gemini Developer key rewrites only this file, and retains the
# inactive provider's key for a later switch back.
if [ ! -f "$acervo_root/llm.env" ]; then
  : >"$acervo_root/llm.env"
fi
chmod 600 "$acervo_root/llm.env"

# A model key used to be written to secrets.env as well, and compose passes llm.env last — so one
# variable was defined in two files and the loser was silent. Move any such line here once. This
# erases itself: after the first run there is nothing left to move.
if grep -q '^GEMINI_API_KEY=' "$acervo_root/secrets.env"; then
  if [ -n "${GEMINI_API_KEY:-}" ] && ! grep -q '^GEMINI_API_KEY=' "$acervo_root/llm.env"; then
    printf 'GEMINI_API_KEY=%s\n' "$GEMINI_API_KEY" >>"$acervo_root/llm.env"
  fi
  secrets_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$secrets_tmp"' EXIT HUP INT TERM
  # `|| true` because grep reports "no lines matched" as a failure, and set -e would take it.
  grep -v '^GEMINI_API_KEY=' "$acervo_root/secrets.env" >"$secrets_tmp" || true
  chmod 600 "$secrets_tmp"
  mv "$secrets_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi
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

if [ -n "$llm_credentials_file" ]; then
  [ -f "$llm_credentials_file" ] || { echo "Missing LLM credentials file" >&2; exit 2; }
  catalogue="$release_dir/models/catalogue.json"
  [ -f "$catalogue" ] || { echo "Missing provider catalogue at $catalogue" >&2; exit 2; }

  # A provider is a row of data, so what may be written here is "a variable some row reads", not a
  # list this script keeps in step by hand. `ACERVO_TEXT_CHAIN` is the one name that belongs to no
  # row. This replaces the old gemini|vertex whitelist: adding a provider is a catalogue edit.
  llm_tmp="$acervo_root/llm.env.tmp.$$"
  names_tmp="$acervo_root/llm.names.$$"
  trap 'rm -f "$llm_tmp" "$names_tmp"' EXIT HUP INT TERM
  : >"$names_tmp"
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] || continue
    case "$line" in
      *=*) ;;
      *) echo "LLM configuration lines must be NAME=VALUE" >&2; exit 2 ;;
    esac
    name=${line%%=*}
    value=${line#*=}
    case "$name" in
      ''|*[!A-Z0-9_]*) echo "Unsafe LLM variable name: $name" >&2; exit 2 ;;
    esac
    case "$value" in
      *[!A-Za-z0-9._:/,-]*) echo "Unsafe LLM configuration value" >&2; exit 2 ;;
    esac
    if [ "$name" != ACERVO_TEXT_CHAIN ] && ! grep -q "\"$name\"" "$catalogue"; then
      echo "$name is not a variable any provider in the catalogue reads" >&2
      exit 2
    fi
    printf '%s\n' "$name" >>"$names_tmp"
  done <"$llm_credentials_file"

  # Only the named lines are rewritten, so a provider that is not being configured keeps its key and
  # can be switched back to without minting a new one.
  awk -F= 'NR == FNR { drop[$0] = 1; next } !($1 in drop)' \
    "$names_tmp" "$acervo_root/llm.env" >"$llm_tmp"
  cat "$llm_credentials_file" >>"$llm_tmp"
  chmod 600 "$llm_tmp"
  mv "$llm_tmp" "$acervo_root/llm.env"
  rm -f "$names_tmp"
  trap - EXIT HUP INT TERM
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
ACERVO_SERVER_DATA=$acervo_root/data/server
ACERVO_MEDIA=$acervo_root/data/media
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

# There is one schema and no upgrade path: a schema change is deployed by rebuilding the database,
# which is the doctrine AGENTS.md already records, and this is it. Accounts go with it and are
# recreated afterwards with `--create-account`. Anki review history lives under --reset-data
# instead: it is irreplaceable, and a schema rebuild must not take it out.
if [ "$reset_database" = true ]; then
  echo "Stopping the server to replace its database..."
  compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file" stop server >/dev/null 2>&1 || true
  # Copied only once the container is stopped: copying a live WAL database is the classic route to
  # a backup that looks fine until the day you need it.
  if [ -d "$acervo_root/data/server" ]; then
    mkdir -p "$backup_dir/server"
    cp -R "$acervo_root/data/server/." "$backup_dir/server/" 2>/dev/null || true
  fi
  rm -rf -- "$acervo_root/data/server"
  mkdir -p "$acervo_root/data/server"
  echo "Vocabulary database replaced; the previous one is in $backup_dir/server"
fi

# Replacing PocketBase renamed the compose service, so an already-deployed server still carries the
# old container — and it still holds the app port, which makes the new one fail to bind with "port is
# already allocated". Compose calls it an orphan and warns rather than removing it, and the warning
# scrolls past in the build output. Retire it here instead. This erases itself: after the first run
# there is nothing left to remove.
#
# Only ever this one container, by exact name. `--remove-orphans` would do the same job and any
# future one, but it decides for itself what in this project is surplus, and that is not a decision
# to hand to a flag on a shared host.
retired_container="$compose_project-pocketbase-1"
if docker inspect "$retired_container" >/dev/null 2>&1; then
  run_quietly "Retiring the superseded $retired_container container" \
    docker rm -f "$retired_container"
  echo "Removed the superseded $retired_container container, which was holding the app port"
  if [ -d "$acervo_root/data/pocketbase" ]; then
    # Left where it is on purpose. The words in it are the owner's, an export is the documented way
    # to carry them across, and deleting the last copy on their behalf is not this script's call.
    echo "Its old database is untouched at $acervo_root/data/pocketbase; remove it when you no longer want it"
  fi
fi

# The other half of that failure, and the nastier one. A create that cannot bind its port leaves the
# container behind in `Created` state, and its host binding is never programmed — not on a later
# start, and not on a restart either. Compose then finds a container whose configuration matches,
# starts it, and reports success; the healthcheck runs *inside* the container, so it goes green while
# nothing is published. Recreating is free — the database is on a mounted volume — so a server
# container that is not running is discarded rather than started.
if docker inspect "$compose_project-server-1" >/dev/null 2>&1 \
   && [ "$(docker inspect -f '{{.State.Running}}' "$compose_project-server-1" 2>/dev/null || echo false)" != true ]; then
  run_quietly "Discarding a stopped server container" docker rm -f "$compose_project-server-1"
fi

echo "Building and starting containers..."
run_quietly "Building and starting containers" compose -p "$compose_project" \
  --env-file "$acervo_root/deployment.env" \
  --env-file "$acervo_root/secrets.env" \
  --env-file "$acervo_root/llm.env" \
  -f "$compose_file" up -d --build anki-sync-server server

echo "Waiting for anki-sync-server to become healthy..."
attempt=0
until [ "$(compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" --env-file "$acervo_root/llm.env" -f "$compose_file" ps --format json anki-sync-server 2>/dev/null | grep -c '"Health":"healthy"' || true)" -gt 0 ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" --env-file "$acervo_root/llm.env" -f "$compose_file" logs anki-sync-server >&2
    exit 1
  fi
  sleep 2
done

echo "Waiting for the server to become healthy..."
attempt=0
until [ "$(compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" --env-file "$acervo_root/llm.env" -f "$compose_file" ps --format json server 2>/dev/null | grep -c '"Health":"healthy"' || true)" -gt 0 ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" --env-file "$acervo_root/llm.env" -f "$compose_file" logs server >&2
    exit 1
  fi
  sleep 2
done

# Asking the container whether it is healthy is not the same question as asking whether anyone can
# reach it: the healthcheck runs inside the container and knows nothing about publishing. This is the
# check that catches a container serving perfectly on a port bound to nothing, which is what the line
# below used to claim its way past. `docker port` rather than an HTTP request on purpose — it is the
# precise signal, and it needs no client this host might not have.
published=$(docker port "$compose_project-server-1" 8000 2>/dev/null || true)
if [ -z "$published" ]; then
  echo "The Acervo server is running but its port is not published, so nothing can reach it." >&2
  echo "Remove the container and deploy again: docker rm -f $compose_project-server-1" >&2
  exit 1
fi

printf '%s\n' "$release_dir" >"$acervo_root/current-release"
echo "Acervo Anki sync server is healthy at $bind_address:$anki_port"
echo "Acervo internal HTTP backend is healthy at http://$app_bind_address:$app_port"
echo "Open the separately configured HTTPS reverse-proxy or Tailscale Serve address; this deployment does not claim the host's default HTTPS endpoint."
