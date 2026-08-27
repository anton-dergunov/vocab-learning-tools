#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=
target=
acervo_root=
configure=false
reset_data=false
remember=false
bind_address=
anki_port=
action=deploy

usage() {
  cat >&2 <<'EOF'
usage:
  ./deploy.sh --local [--root PATH] [--bind-address ADDRESS] [--port PORT]
              [--configure-credentials] [--reset-data]
  ./deploy.sh [--target USER@HOST] [--root PATH] [--configure-credentials]
              [--bind-address ADDRESS] [--port PORT] [--remember-target]
              [--reset-data]
  ./deploy.sh [--local | --target USER@HOST] --status
EOF
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --local) mode=local; shift ;;
    --target) [ "$#" -ge 2 ] || usage; target=$2; shift 2 ;;
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --configure-credentials) configure=true; shift ;;
    --remember-target) remember=true; shift ;;
    --bind-address) [ "$#" -ge 2 ] || usage; bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; anki_port=$2; shift 2 ;;
    --status) action=status; shift ;;
    --reset-data) reset_data=true; shift ;;
    *) usage ;;
  esac
done
case "$bind_address" in *[!A-Za-z0-9:._-]*) echo "Unsafe bind address" >&2; exit 2 ;; esac
case "$anki_port" in ""|*[!0-9]*) [ -z "$anki_port" ] || { echo "Port must be numeric" >&2; exit 2; } ;; esac
if [ -n "$anki_port" ] && { [ "$anki_port" -lt 1 ] || [ "$anki_port" -gt 65535 ]; }; then
  echo "Port must be between 1 and 65535" >&2
  exit 2
fi

if [ "$reset_data" = true ]; then
  printf '%s' 'Type RESET ACERVO DATA to permanently replace server and robot data: '
  IFS= read -r reset_confirmation
  [ "$reset_confirmation" = 'RESET ACERVO DATA' ] || {
    echo "Reset cancelled" >&2
    exit 2
  }
fi

prompt_credentials() {
  printf '%s' 'Initial Anki sync username: ' >&2
  IFS= read -r sync_username
  printf '%s' 'Initial Anki sync password: ' >&2
  if [ -t 0 ]; then
    stty -echo
    trap 'stty echo' EXIT HUP INT TERM
    IFS= read -r sync_password
    stty echo
    trap - EXIT HUP INT TERM
  else
    IFS= read -r sync_password
  fi
  printf '\n' >&2
  [ -n "$sync_username" ] && [ -n "$sync_password" ] || {
    echo "Username and password are required" >&2
    exit 2
  }
  case "$sync_username$sync_password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
}

if [ "$mode" = local ]; then
  if [ "$action" = status ]; then
    docker inspect \
      --format='state={{.State.Status}}, health={{.State.Health.Status}}' \
      acervo-anki-sync-server-1
    docker port acervo-anki-sync-server-1 8080
    exit 0
  fi
  [ -n "$acervo_root" ] || acervo_root=${ACERVO_LOCAL_ROOT:-"$HOME/.acervo"}
  local_archive=$($repo_root/scripts/package_acervo_server.sh)
  credential_args=
  if [ "$configure" = true ] || [ ! -f "$acervo_root/secrets.env" ]; then
    prompt_credentials
    credential_args=--credentials-stdin
  fi
  set -- --root "$acervo_root" --archive "$local_archive"
  [ -z "$bind_address" ] || set -- "$@" --bind-address "$bind_address"
  [ -z "$anki_port" ] || set -- "$@" --port "$anki_port"
  [ -z "$credential_args" ] || set -- "$@" "$credential_args"
  [ "$reset_data" = false ] || set -- "$@" --reset-data
  if [ -n "$credential_args" ]; then
    printf '%s\n%s\n' "$sync_username" "$sync_password" | "$repo_root/deploy/acervo/install.sh" "$@"
  else
    "$repo_root/deploy/acervo/install.sh" "$@"
  fi
  exit 0
fi

if [ -z "$target" ] && [ -f "$repo_root/.acervo-deploy" ]; then
  IFS= read -r target <"$repo_root/.acervo-deploy"
fi
[ -n "$target" ] || usage
case "$target" in *[!A-Za-z0-9_.@:-]*) echo "Unsafe SSH target" >&2; exit 2 ;; esac
if [ -n "$acervo_root" ]; then
  case "$acervo_root" in /*) ;; *) echo "Remote root must be absolute" >&2; exit 2 ;; esac
  case "$acervo_root" in *[!A-Za-z0-9_./-]*) echo "Unsafe remote root" >&2; exit 2 ;; esac
fi
if [ "$remember" = true ]; then
  printf '%s\n' "$target" >"$repo_root/.acervo-deploy"
  chmod 600 "$repo_root/.acervo-deploy"
fi

if [ "$action" = status ]; then
  ssh -t "$target" \
    'docker_path=$(command -v docker || true); \
     [ -n "$docker_path" ] || docker_path=/var/packages/ContainerManager/target/usr/bin/docker; \
     if [ "$(id -u)" -eq 0 ]; then privilege=; else privilege=sudo; fi; \
     $privilege "$docker_path" inspect \
       --format=state={{.State.Status}},health={{.State.Health.Status}} \
       acervo-anki-sync-server-1 && \
     $privilege "$docker_path" port acervo-anki-sync-server-1 8080'
  exit 0
fi

archive=$($repo_root/scripts/package_acervo_server.sh)
remote_archive="/tmp/acervo-release-$$.tar.gz"
remote_installer="/tmp/acervo-install-$$.sh"
remote_credentials="/tmp/acervo-credentials-$$"

remote_cleanup() {
  ssh -T "$target" "rm -f $remote_archive $remote_installer $remote_credentials" \
    >/dev/null 2>&1 || true
}

remote_failed() {
  remote_cleanup
  echo "Acervo deployment failed on the remote server" >&2
  exit 1
}

echo "Streaming the Acervo release over SSH..."
ssh -T "$target" "umask 077 && cat > $remote_archive" <"$archive" || remote_failed
ssh -T "$target" "umask 077 && cat > $remote_installer" \
  <"$repo_root/deploy/acervo/install.sh" || remote_failed

credential_args=
if [ "$configure" = true ]; then
  prompt_credentials
  printf '%s\n%s\n' "$sync_username" "$sync_password" | \
    ssh -T "$target" "umask 077 && cat > $remote_credentials" || remote_failed
  credential_args="--credentials-file $remote_credentials"
fi

installer_arguments="--archive $remote_archive"
if [ -n "$acervo_root" ]; then
  installer_arguments="$installer_arguments --root $acervo_root"
fi
[ -z "$credential_args" ] || installer_arguments="$installer_arguments $credential_args"
[ -z "$bind_address" ] || installer_arguments="$installer_arguments --bind-address $bind_address"
[ -z "$anki_port" ] || installer_arguments="$installer_arguments --port $anki_port"
[ "$reset_data" = false ] || installer_arguments="$installer_arguments --reset-data"

echo "Installing on the remote server (sudo may ask for its password)..."
ssh -t "$target" \
  "if [ \"\$(id -u)\" -eq 0 ]; then run=sh; else run='sudo sh'; fi; \
   \$run $remote_installer $installer_arguments; \
   status=\$?; rm -f $remote_archive $remote_installer $remote_credentials; exit \$status" \
  || remote_failed
