#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
profile=${ACERVO_DEPLOY_PROFILE:-"$repo_root/.acervo-deploy"}
helper_path=/usr/local/sbin/deploy-acervo
helper_protocol=3

mode=
target=
acervo_root=
configure=false
reset_data=false
reset_pocketbase=false
remember=false
bind_address=
anki_port=
app_bind_address=
app_port=
https_port=
service=
action=deploy

usage() {
  cat >&2 <<'EOF'
usage:
  ./deploy.sh --local [--root PATH] [--bind-address ADDRESS] [--port PORT]
              [--app-bind-address ADDRESS] [--app-port PORT]
              [--configure-credentials] [--reset-data] [--reset-pocketbase]
  ./deploy.sh [--target USER@HOST] [--root PATH] [--configure-credentials]
              [--bind-address ADDRESS] [--port PORT] [--remember-target]
              [--app-bind-address ADDRESS] [--app-port PORT]
              [--https-port PORT] [--service NAME] [--reset-data] [--reset-pocketbase]
  ./deploy.sh [--target USER@HOST] [--remember-target] --install-helper
  ./deploy.sh [--target USER@HOST] [--https-port PORT | --service NAME] --configure-https
  ./deploy.sh [--local | --target USER@HOST] --status

  --service NAME      publish through the Tailscale service svc:NAME on its own
                      hostname and its own 443, instead of a host port. Needed
                      for Android to install this app alongside another PWA on
                      the same machine; takes precedence over --https-port
  --reset-data        replace the Anki sync server and robot collections
  --reset-pocketbase  replace the vocabulary database, so a rewritten bootstrap
                      migration is applied from scratch; Anki data is untouched
EOF
  exit 2
}

choose_action() {
  [ "$action" = deploy ] || usage
  action=$1
}

# A step says what stage it is in and what it produced; a bundler's asset table says neither, so it
# is kept until it is worth reading. On failure everything the step wrote is printed before the
# script stops. Deliberately not a pipeline: this is POSIX sh, where pipefail does not exist and a
# pipe would discard the step's own exit status.
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

while [ "$#" -gt 0 ]; do
  case "$1" in
    --local) mode=local; shift ;;
    --target) [ "$#" -ge 2 ] || usage; target=$2; shift 2 ;;
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --configure-credentials) configure=true; shift ;;
    --remember-target) remember=true; shift ;;
    --bind-address) [ "$#" -ge 2 ] || usage; bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; anki_port=$2; shift 2 ;;
    --app-bind-address) [ "$#" -ge 2 ] || usage; app_bind_address=$2; shift 2 ;;
    --app-port) [ "$#" -ge 2 ] || usage; app_port=$2; shift 2 ;;
    --https-port) [ "$#" -ge 2 ] || usage; https_port=$2; shift 2 ;;
    --service) [ "$#" -ge 2 ] || usage; service=$2; shift 2 ;;
    --install-helper) choose_action install-helper; shift ;;
    --configure-https) choose_action configure-https; shift ;;
    --status) choose_action status; shift ;;
    --reset-data) reset_data=true; shift ;;
    --reset-pocketbase) reset_pocketbase=true; shift ;;
    *) usage ;;
  esac
done

read_profile() {
  [ -f "$profile" ] || return 0
  first_line=$(sed -n '/[^[:space:]]/ { p; q; }' "$profile")
  case "$first_line" in
    *=*)
      while IFS='=' read -r key value; do
        case "$key" in
          ''|'#'*) continue ;;
          DEPLOY_TARGET) profile_target=$value ;;
          ACERVO_ROOT) profile_root=$value ;;
          ACERVO_BIND_ADDRESS) profile_bind_address=$value ;;
          ACERVO_ANKI_PORT) profile_anki_port=$value ;;
          ACERVO_APP_BIND_ADDRESS) profile_app_bind_address=$value ;;
          ACERVO_APP_PORT) profile_app_port=$value ;;
          ACERVO_HTTPS_PORT) profile_https_port=$value ;;
          ACERVO_SERVICE) profile_service=$value ;;
          *) echo "Unknown setting in .acervo-deploy: $key" >&2; exit 2 ;;
        esac
      done <"$profile"
      ;;
    *) profile_target=$first_line ;;
  esac
}

validate_address() {
  label=$1
  value=$2
  case "$value" in
    ''|*[!A-Za-z0-9:._-]*) echo "Unsafe $label" >&2; exit 2 ;;
  esac
}

validate_port() {
  label=$1
  value=$2
  case "$value" in
    ''|*[!0-9]*) echo "$label must be numeric" >&2; exit 2 ;;
  esac
  if [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
    echo "$label must be between 1 and 65535" >&2
    exit 2
  fi
}

write_profile() {
  umask 077
  {
    printf 'DEPLOY_TARGET=%s\n' "$target"
    printf 'ACERVO_ROOT=%s\n' "$acervo_root"
    printf 'ACERVO_BIND_ADDRESS=%s\n' "$effective_bind_address"
    printf 'ACERVO_ANKI_PORT=%s\n' "$effective_anki_port"
    printf 'ACERVO_APP_BIND_ADDRESS=%s\n' "$effective_app_bind_address"
    printf 'ACERVO_APP_PORT=%s\n' "$effective_app_port"
    printf 'ACERVO_HTTPS_PORT=%s\n' "$effective_https_port"
    printf 'ACERVO_SERVICE=%s\n' "$service"
  } >"$profile"
  chmod 600 "$profile"
}

profile_target=
profile_root=
profile_bind_address=
profile_anki_port=
profile_app_bind_address=
profile_app_port=
profile_https_port=
profile_service=
if [ "$mode" != local ]; then
  read_profile
  target=${target:-$profile_target}
  acervo_root=${acervo_root:-$profile_root}
  bind_address=${bind_address:-$profile_bind_address}
  anki_port=${anki_port:-$profile_anki_port}
  app_bind_address=${app_bind_address:-$profile_app_bind_address}
  app_port=${app_port:-$profile_app_port}
  https_port=${https_port:-$profile_https_port}
  service=${service:-$profile_service}
fi

effective_bind_address=${bind_address:-127.0.0.1}
effective_anki_port=${anki_port:-27701}
effective_app_bind_address=${app_bind_address:-127.0.0.1}
effective_app_port=${app_port:-27702}
effective_https_port=${https_port:-27702}
validate_address "bind address" "$effective_bind_address"
validate_address "app bind address" "$effective_app_bind_address"
validate_port "Anki port" "$effective_anki_port"
validate_port "App port" "$effective_app_port"
validate_port "HTTPS port" "$effective_https_port"
# A Tailscale service listens on its own virtual IP, so its 443 is not the host's 443 and cannot
# collide with another application. Android only mints a WebAPK for a default port, so a service is
# what lets Acervo install alongside another self-hosted PWA rather than replacing it.
if [ -n "$service" ]; then
  case "$service" in
    ''|*[!a-z0-9-]*)
      echo "The service name must use lowercase letters, digits and hyphens" >&2
      exit 2
      ;;
  esac
fi
[ "$effective_anki_port" != "$effective_app_port" ] || {
  echo "The Acervo app/PocketBase port must differ from the Anki sync port" >&2
  exit 2
}

if [ "$mode" = local ] && { [ "$action" = install-helper ] || [ "$action" = configure-https ]; }; then
  usage
fi
if [ "$configure" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$reset_data" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$reset_pocketbase" = true ] && [ "$action" != deploy ]; then usage; fi

if [ "$reset_data" = true ]; then
  printf '%s' 'Type RESET ACERVO DATA to permanently replace server and robot data: '
  IFS= read -r reset_confirmation
  [ "$reset_confirmation" = 'RESET ACERVO DATA' ] || {
    echo "Reset cancelled" >&2
    exit 2
  }
fi

if [ "$reset_pocketbase" = true ]; then
  echo 'This replaces the vocabulary database. Every account, word and revision on the server is'
  echo 'discarded; accounts must be recreated afterwards. Device replicas are not touched, and a'
  echo 'copy of the old database is kept under the deployment backups directory.'
  printf '%s' 'Type RESET ACERVO VOCABULARY to continue: '
  IFS= read -r reset_pocketbase_confirmation
  [ "$reset_pocketbase_confirmation" = 'RESET ACERVO VOCABULARY' ] || {
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
  printf '%s' 'Initial PocketBase superuser email: ' >&2
  IFS= read -r pb_superuser_email
  printf '%s' 'Initial PocketBase superuser password: ' >&2
  if [ -t 0 ]; then
    stty -echo
    trap 'stty echo' EXIT HUP INT TERM
    IFS= read -r pb_superuser_password
    stty echo
    trap - EXIT HUP INT TERM
  else
    IFS= read -r pb_superuser_password
  fi
  printf '\n' >&2
  [ -n "$pb_superuser_email" ] && [ -n "$pb_superuser_password" ] || {
    echo "PocketBase superuser email and password are required" >&2
    exit 2
  }
  # Optional: without it the server simply reports that it cannot build entries, and every other
  # part of Acervo works exactly as before.
  printf '%s' 'Gemini API key for capture (blank to disable capture): ' >&2
  if [ -t 0 ]; then
    stty -echo
    trap 'stty echo' EXIT HUP INT TERM
    IFS= read -r gemini_api_key
    stty echo
    trap - EXIT HUP INT TERM
  else
    IFS= read -r gemini_api_key || gemini_api_key=""
  fi
  printf '\n' >&2
}

build_release_archive() {
  eval "$("$repo_root/scripts/version.sh")"
  export ACERVO_APP_VERSION ACERVO_APP_BUILD
  if [ "$(uname -s)" = Darwin ] && [ "${ACERVO_SKIP_MACOS_RELEASE:-false}" != true ]; then
    "$repo_root/scripts/package_macos_release.sh" >&2
    ACERVO_INCLUDE_MACOS_RELEASE=true
  else
    ACERVO_INCLUDE_MACOS_RELEASE=false
  fi
  export ACERVO_INCLUDE_MACOS_RELEASE
  if [ "${ACERVO_SKIP_APP_BUILD:-false}" != true ]; then
    echo "Building the web app..." >&2
    run_quietly "The web build" npm run stage:pwa
  fi
  "$repo_root/scripts/package_acervo_server.sh"
}

if [ "$mode" = local ]; then
  if [ "$action" = status ]; then
    docker inspect --format='state={{.State.Status}}, health={{.State.Health.Status}}' acervo-anki-sync-server-1
    docker port acervo-anki-sync-server-1 8080
    docker inspect --format='state={{.State.Status}}, health={{.State.Health.Status}}' acervo-pocketbase-1
    docker port acervo-pocketbase-1 8090
    exit 0
  fi
  [ -n "$acervo_root" ] || acervo_root=${ACERVO_LOCAL_ROOT:-"$HOME/.acervo"}
  local_archive=$(build_release_archive)
  credential_args=
  if [ "$configure" = true ] || [ ! -f "$acervo_root/secrets.env" ]; then
    prompt_credentials
    credential_args=--credentials-stdin
  fi
  set -- --root "$acervo_root" --archive "$local_archive" \
    --bind-address "$effective_bind_address" --port "$effective_anki_port" \
    --app-bind-address "$effective_app_bind_address" --app-port "$effective_app_port"
  [ -z "$credential_args" ] || set -- "$@" "$credential_args"
  [ "$reset_data" = false ] || set -- "$@" --reset-data
  [ "$reset_pocketbase" = false ] || set -- "$@" --reset-pocketbase
  if [ -n "$credential_args" ]; then
    printf '%s\n%s\n%s\n%s\n%s\n' "$sync_username" "$sync_password" "$pb_superuser_email" "$pb_superuser_password" "$gemini_api_key" | "$repo_root/deploy/acervo/install.sh" "$@"
  else
    "$repo_root/deploy/acervo/install.sh" "$@"
  fi
  exit 0
fi

[ -n "$target" ] || usage
case "$target" in *[!A-Za-z0-9_.@:-]*) echo "Unsafe SSH target" >&2; exit 2 ;; esac
if [ -n "$acervo_root" ]; then
  case "$acervo_root" in /*/acervo) ;; *) echo "Remote root must be an absolute path ending in /acervo" >&2; exit 2 ;; esac
  case "$acervo_root" in *[!A-Za-z0-9_./-]*) echo "Unsafe remote root" >&2; exit 2 ;; esac
fi
if [ "$remember" = true ]; then write_profile; fi

if [ "$action" = install-helper ]; then
  remote_helper="/tmp/deploy-acervo-$$"
  echo "Uploading the reviewed Acervo deployment launcher..."
  ssh -T "$target" "umask 077 && cat > $remote_helper" <"$repo_root/deploy/acervo/remote-helper.sh"
  echo "Installing the launcher (sudo asks once; routine deployments will not)..."
  ssh -t "$target" \
    "sudo sh $remote_helper --install; result=\$?; rm -f $remote_helper; exit \$result"
  exit 0
fi

remote_probe=$(ssh -T "$target" \
  "if [ \"\$(id -u)\" -eq 0 ]; then echo root; \
   elif report=\$(sudo -n $helper_path check 2>/dev/null) && \
        [ \"\$report\" = 'acervo-deploy-protocol: $helper_protocol' ]; then echo helper; \
   else echo missing; fi")
remote_mode=$(printf '%s\n' "$remote_probe" | tail -n 1)
case "$remote_mode" in
  root|helper) ;;
  *)
    echo "The passwordless Acervo launcher is missing or incompatible on $target." >&2
    echo "Install or refresh it once with: ./deploy.sh --install-helper" >&2
    exit 1
    ;;
esac

if [ "$action" = status ]; then
  if [ "$remote_mode" = root ]; then
    ssh -T "$target" 'docker_path=$(command -v docker || true); \
      [ -n "$docker_path" ] || docker_path=/var/packages/ContainerManager/target/usr/bin/docker; \
      "$docker_path" inspect --format=state={{.State.Status}},health={{.State.Health.Status}} acervo-anki-sync-server-1 && \
      "$docker_path" port acervo-anki-sync-server-1 8080 && \
      "$docker_path" inspect --format=state={{.State.Status}},health={{.State.Health.Status}} acervo-pocketbase-1 && \
      "$docker_path" port acervo-pocketbase-1 8090'
  else
    ssh -T "$target" "sudo -n $helper_path status"
  fi
  exit 0
fi

if [ "$action" = configure-https ]; then
  # The service and the host-port listener are alternatives, not layers. A configured service owns
  # the public address, and the remembered HTTPS port is left unused rather than mapped as well.
  if [ -n "$service" ]; then
    https_arguments="--service $service"
    echo "Configuring the Tailscale service svc:$service (HTTPS 443)."
  else
    https_arguments="--https-port $effective_https_port"
  fi
  if [ "$remote_mode" = root ]; then
    ssh -T "$target" "sh -s -- configure-https $https_arguments --app-port $effective_app_port" \
      <"$repo_root/deploy/acervo/remote-helper.sh"
  else
    ssh -T "$target" \
      "sudo -n $helper_path configure-https $https_arguments --app-port $effective_app_port"
  fi
  exit 0
fi

archive=$(build_release_archive)
remote_installer="/tmp/acervo-install-$$.sh"
remote_archive="/tmp/acervo-release-$$.tar.gz"
remote_credentials="/tmp/acervo-credentials-$$"
remote_cleanup() {
  ssh -T "$target" "rm -f $remote_installer $remote_archive $remote_credentials" >/dev/null 2>&1 || true
}
remote_failed() {
  remote_cleanup
  echo "Acervo deployment failed on the remote server" >&2
  exit 1
}

credential_args=
if [ "$configure" = true ]; then
  prompt_credentials
  printf '%s\n%s\n%s\n%s\n' "$sync_username" "$sync_password" "$pb_superuser_email" "$pb_superuser_password" | \
    ssh -T "$target" "umask 077 && cat > $remote_credentials" || remote_failed
  credential_args="--credentials-file $remote_credentials"
fi

installer_arguments=
[ -z "$acervo_root" ] || installer_arguments="$installer_arguments --root $acervo_root"
[ -z "$credential_args" ] || installer_arguments="$installer_arguments $credential_args"
installer_arguments="$installer_arguments --bind-address $effective_bind_address --port $effective_anki_port"
installer_arguments="$installer_arguments --app-bind-address $effective_app_bind_address --app-port $effective_app_port"
[ "$reset_data" = false ] || installer_arguments="$installer_arguments --reset-data"
[ "$reset_pocketbase" = false ] || installer_arguments="$installer_arguments --reset-pocketbase"

if [ "$remote_mode" = helper ]; then
  echo "Streaming and installing with the passwordless Acervo launcher..."
  ssh -T "$target" "sudo -n $helper_path deploy$installer_arguments" <"$archive" || remote_failed
else
  echo "Streaming the Acervo release over SSH as root..."
  ssh -T "$target" "umask 077 && cat > $remote_archive" <"$archive" || remote_failed
  ssh -T "$target" "umask 077 && cat > $remote_installer" <"$repo_root/deploy/acervo/install.sh" || remote_failed
  ssh -T "$target" \
    "sh $remote_installer --archive $remote_archive$installer_arguments; \
     result=\$?; rm -f $remote_installer $remote_archive $remote_credentials; exit \$result" || remote_failed
fi

echo "Acervo deployment completed."
echo "Internal HTTP backend: http://$effective_app_bind_address:$effective_app_port"
if [ -n "$service" ]; then
  echo "Dedicated Tailscale service: svc:$service on HTTPS 443 (configure explicitly with ./deploy.sh --configure-https)"
else
  echo "Dedicated Tailscale HTTPS listener: port $effective_https_port (configure explicitly with ./deploy.sh --configure-https)"
fi
