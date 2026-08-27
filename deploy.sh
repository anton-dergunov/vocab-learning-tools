#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=
target=
acervo_root=
configure=false
reset_data=false
remember=false

usage() {
  cat >&2 <<'EOF'
usage:
  ./deploy.sh --local [--root PATH] [--configure-credentials] [--reset-data]
  ./deploy.sh [--target USER@HOST] [--root PATH] [--configure-credentials]
              [--remember-target] [--reset-data]
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
    --reset-data) reset_data=true; shift ;;
    *) usage ;;
  esac
done

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
  stty -echo
  trap 'stty echo' EXIT HUP INT TERM
  IFS= read -r sync_password
  stty echo
  trap - EXIT HUP INT TERM
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
  [ -n "$acervo_root" ] || acervo_root=${ACERVO_LOCAL_ROOT:-"$HOME/.acervo"}
  local_archive=$($repo_root/scripts/package_acervo_server.sh)
  credential_args=
  if [ "$configure" = true ] || [ ! -f "$acervo_root/secrets.env" ]; then
    prompt_credentials
    credential_args=--credentials-stdin
  fi
  set -- --root "$acervo_root" --archive "$local_archive"
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
if [ "$remember" = true ]; then
  printf '%s\n' "$target" >"$repo_root/.acervo-deploy"
  chmod 600 "$repo_root/.acervo-deploy"
fi

archive=$($repo_root/scripts/package_acervo_server.sh)
remote_archive="/tmp/acervo-release-$$.tar.gz"
remote_installer="/tmp/acervo-install-$$.sh"
scp "$archive" "$target:$remote_archive"
scp "$repo_root/deploy/acervo/install.sh" "$target:$remote_installer"

credential_args=
if [ "$configure" = true ]; then
  prompt_credentials
  credential_args=--credentials-stdin
fi

remote_command="sudo sh $remote_installer --archive $remote_archive"
if [ -n "$acervo_root" ]; then
  case "$acervo_root" in /*) ;; *) echo "Remote root must be absolute" >&2; exit 2 ;; esac
  case "$acervo_root" in *[!A-Za-z0-9_./-]*) echo "Unsafe remote root" >&2; exit 2 ;; esac
  remote_command="$remote_command --root $acervo_root"
fi
[ -z "$credential_args" ] || remote_command="$remote_command --credentials-stdin"
[ "$reset_data" = false ] || remote_command="$remote_command --reset-data"

if [ -n "$credential_args" ]; then
  printf '%s\n%s\n' "$sync_username" "$sync_password" | ssh -T "$target" "$remote_command"
else
  ssh -t "$target" "$remote_command"
fi

ssh -T "$target" "rm -f $remote_archive $remote_installer"
