#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
remote-channel.sh --ssh-host HOST --remote-root PATH ACTION [options]

Control a persistent remote tmux session for one Android source tree.

Required:
  --ssh-host HOST       Remote SSH target.
  --remote-root PATH    Remote Android source root.

Actions:
  check                 Check SSH, tmux, and remote root readiness.
  install-tmux          Install tmux on the remote host when missing.
  ensure                Create or reuse the remote session.
  run -- COMMAND        Send COMMAND to the session.
  status                Print session and current command status.
  tail                  Tail the latest or selected command log.
  stop                  Kill the remote session.

Run options:
  --lock none|exclusive Default: none. Use exclusive for edits, git writes, and builds.
  --no-wait             Return after dispatching the command.
  --command-id ID       Optional stable command id.

Tail options:
  --command-id ID       Tail a specific command log.
  --lines N             Default: 120.

Install options:
  --sudo-password-env NAME
                         Env var containing remote sudo password.
                         Default: CODEX_REMOTE_SUDO_PASSWORD.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

single_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

hash_id() {
  printf "%s" "$1" | sha256sum | awk '{print substr($1, 1, 12)}'
}

prepare_ssh_opts() {
  SSH_OPTS=(
    -o BatchMode=no
    -o ConnectTimeout="${CODEX_REMOTE_CHANNEL_CONNECT_TIMEOUT:-8}"
    -o ServerAliveInterval="${CODEX_REMOTE_CHANNEL_SERVER_ALIVE_INTERVAL:-30}"
    -o ServerAliveCountMax="${CODEX_REMOTE_CHANNEL_SERVER_ALIVE_COUNT_MAX:-3}"
  )
  if [[ "${CODEX_REMOTE_CHANNEL_SSH_MUX:-1}" != "0" ]]; then
    local control_dir="${CODEX_REMOTE_CHANNEL_CONTROL_DIR:-$HOME/.ssh/controlmasters}"
    mkdir -p "$control_dir" 2>/dev/null || true
    chmod 700 "$control_dir" 2>/dev/null || true
    SSH_OPTS+=(
      -o ControlMaster=auto
      -o ControlPersist="${CODEX_REMOTE_CHANNEL_CONTROL_PERSIST:-2h}"
      -o ControlPath="${CODEX_REMOTE_CHANNEL_CONTROL_PATH:-$control_dir/codex-%C}"
    )
  fi
}

ssh_run() {
  local cmd="$1"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "$cmd"
}

ssh_run_capture() {
  local cmd="$1"
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "$cmd" 2>&1
}

ssh_run_capture_with_stdin() {
  local cmd="$1"
  local input="$2"
  printf "%s\n" "$input" | ssh "${SSH_OPTS[@]}" "$SSH_HOST" "$cmd" 2>&1
}

SSH_HOST=""
REMOTE_ROOT=""
ACTION=""
LOCK_MODE="none"
WAIT=true
COMMAND_ID=""
TAIL_LINES="120"
SUDO_PASSWORD_ENV="CODEX_REMOTE_SUDO_PASSWORD"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) SSH_HOST="${2:-}"; shift 2 ;;
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --lock) LOCK_MODE="${2:-}"; shift 2 ;;
    --no-wait) WAIT=false; shift ;;
    --command-id) COMMAND_ID="${2:-}"; shift 2 ;;
    --lines) TAIL_LINES="${2:-}"; shift 2 ;;
    --sudo-password-env) SUDO_PASSWORD_ENV="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    check|install-tmux|ensure|run|status|tail|stop) ACTION="$1"; shift; break ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$SSH_HOST" ]] || die "--ssh-host is required"
[[ -n "$REMOTE_ROOT" ]] || die "--remote-root is required"
[[ -n "$ACTION" ]] || die "action is required"
[[ "$REMOTE_ROOT" == /* ]] || die "--remote-root must be absolute"
[[ "$LOCK_MODE" == "none" || "$LOCK_MODE" == "exclusive" ]] || die "--lock must be none or exclusive"
[[ "$TAIL_LINES" =~ ^[0-9]+$ ]] || die "--lines must be a positive integer"

prepare_ssh_opts

SESSION_HASH="$(hash_id "$SSH_HOST|$REMOTE_ROOT")"
SESSION_NAME="codex-android-$SESSION_HASH"
STATE_DIR=".codex/android-remote-sessions/$SESSION_HASH"

remote_state_path() {
  printf "\$HOME/%s" "$STATE_DIR"
}

tmux_install_body() {
  cat <<'REMOTE'
set -e
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y tmux
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y tmux
elif command -v yum >/dev/null 2>&1; then
  yum install -y tmux
elif command -v zypper >/dev/null 2>&1; then
  zypper --non-interactive install tmux
else
  echo 'PACKAGE_MANAGER_UNSUPPORTED install tmux manually' >&2
  exit 11
fi
REMOTE
}

remote_tmux_install_passwordless_command() {
  local install_body_q
  install_body_q="$(single_quote "$(tmux_install_body)")"
  cat <<REMOTE
set -e
if command -v tmux >/dev/null 2>&1; then
  printf 'TMUX_OK path=%s\n' "\$(command -v tmux)"
  tmux -V
  exit 0
fi
command -v sudo >/dev/null 2>&1 || { echo 'SUDO_MISSING install tmux manually' >&2; exit 13; }
if ! sudo -n true >/dev/null 2>&1; then
  echo 'REMOTE_SUDO_PASSWORD_REQUIRED env=$SUDO_PASSWORD_ENV action=install_tmux' >&2
  exit 10
fi
sudo -n sh -c $install_body_q
printf 'TMUX_INSTALLED version=%s path=%s\n' "\$(tmux -V)" "\$(command -v tmux)"
REMOTE
}

remote_tmux_install_password_command() {
  local install_body_q
  install_body_q="$(single_quote "$(tmux_install_body)")"
  cat <<REMOTE
set -e
if command -v tmux >/dev/null 2>&1; then
  printf 'TMUX_OK path=%s\n' "\$(command -v tmux)"
  tmux -V
  exit 0
fi
command -v sudo >/dev/null 2>&1 || { echo 'SUDO_MISSING install tmux manually' >&2; exit 13; }
if ! sudo -S -p '' -v >/dev/null 2>&1; then
  echo 'REMOTE_SUDO_AUTH_FAILED' >&2
  exit 12
fi
sudo -n sh -c $install_body_q
printf 'TMUX_INSTALLED version=%s path=%s\n' "\$(tmux -V)" "\$(command -v tmux)"
REMOTE
}

add_unique_password_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local existing
  for existing in "${PASSWORD_FILES[@]}"; do
    [[ "$existing" == "$file" ]] && return 0
  done
  PASSWORD_FILES+=("$file")
}

add_unique_cred_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local existing
  for existing in "${CRED_FILES[@]}"; do
    [[ "$existing" == "$file" ]] && return 0
  done
  CRED_FILES+=("$file")
}

account_hash() {
  printf "%s@%s" "$1" "$2" | sha256sum | awk '{print $1}'
}

server_for_share() {
  local share="$1"
  share="${share#//}"
  printf "%s" "${share%%/*}"
}

add_account_credential_candidates() {
  local user="$1"
  local server="$2"
  [[ -n "$user" && -n "$server" ]] || return 0
  local key credentials_dir
  credentials_dir="${ANDROID_WSL_SOURCE_ACCESS_CREDENTIALS_DIR:-$HOME/.codex/android-wsl-source-access-info/credentials}"
  key="$(account_hash "$user" "$server")"
  add_unique_password_file "$credentials_dir/$key.passwords.env"
  add_unique_cred_file "$credentials_dir/$key.cred"
}

ssh_host_matches() {
  local candidate="$1"
  [[ -z "$candidate" || "$candidate" == "$SSH_HOST" || "${candidate#*@}" == "${SSH_HOST#*@}" ]]
}

collect_wsl_source_access_credentials() {
  local registry_dir remote_root_norm registry
  registry_dir="${ANDROID_WSL_SOURCE_ACCESS_PROJECTS_DIR:-$HOME/.codex/android-wsl-source-access-info/projects}"
  remote_root_norm="${REMOTE_ROOT%/}"
  [[ -d "$registry_dir" ]] || return 0
  for registry in "$registry_dir"/*.env; do
    [[ -f "$registry" ]] || continue
    while IFS=$'\t' read -r kind value extra; do
      case "$kind" in
        account) add_account_credential_candidates "$value" "$extra" ;;
        cred) add_unique_cred_file "$value" ;;
      esac
    done < <(
      SSH_HOST_VALUE="$SSH_HOST" REMOTE_ROOT_VALUE="$remote_root_norm" REGISTRY_FILE="$registry" bash -c '
set +u
SAMBA_USER=""
SAMBA_CREDENTIALS_FILE=""
REMOTE_SSH_HOSTS=()
REMOTE_ROOTS=()
SAMBA_PROJECT_SHARES=()
source "$REGISTRY_FILE" 2>/dev/null || exit 0
for i in "${!REMOTE_ROOTS[@]}"; do
  root="${REMOTE_ROOTS[$i]%/}"
  host="${REMOTE_SSH_HOSTS[$i]-}"
  if [ "$root" = "$REMOTE_ROOT_VALUE" ] && { [ -z "$host" ] || [ "$host" = "$SSH_HOST_VALUE" ] || [ "${host#*@}" = "${SSH_HOST_VALUE#*@}" ]; }; then
    share="${SAMBA_PROJECT_SHARES[$i]-}"
    if [ -n "$SAMBA_USER" ] && [ -n "$share" ]; then
      share_body="${share#//}"
      server="${share_body%%/*}"
      printf "account\t%s\t%s\n" "$SAMBA_USER" "$server"
    fi
    if [ -n "$SAMBA_CREDENTIALS_FILE" ]; then
      printf "cred\t%s\t\n" "$SAMBA_CREDENTIALS_FILE"
    fi
  fi
done
'
    )
  done
}

collect_ssh_config_credentials() {
  local ssh_user ssh_hostname host_part user_part
  host_part="${SSH_HOST#*@}"
  user_part=""
  if [[ "$SSH_HOST" == *@* ]]; then
    user_part="${SSH_HOST%@*}"
  fi
  while read -r key value _; do
    case "$key" in
      user) ssh_user="$value" ;;
      hostname) ssh_hostname="$value" ;;
    esac
  done < <(ssh -G "$SSH_HOST" 2>/dev/null || true)
  [[ -n "${user_part:-}" ]] && add_account_credential_candidates "$user_part" "$host_part"
  [[ -n "${ssh_user:-}" && -n "${host_part:-}" ]] && add_account_credential_candidates "$ssh_user" "$host_part"
  [[ -n "${ssh_user:-}" && -n "${ssh_hostname:-}" ]] && add_account_credential_candidates "$ssh_user" "$ssh_hostname"
}

read_saved_password_var() {
  local file="$1"
  local var_name="$2"
  [[ -f "$file" ]] || return 0
  VAR_NAME="$var_name" bash -c '
set +u
SAVED_SSH_PASSWORD=""
SAVED_SAMBA_PASSWORD=""
SAVED_REMOTE_SUDO_PASSWORD=""
SAVED_LOCAL_SUDO_PASSWORD=""
source "$1" 2>/dev/null || exit 0
printf "%s" "${!VAR_NAME-}"
' bash "$file"
}

read_cred_password() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  awk -F= '$1=="password"{sub(/^password=/,""); gsub(/\r$/,""); print; exit}' "$file"
}

try_tmux_password_candidate() {
  local source_label="$1"
  local password="$2"
  [[ -n "$password" ]] || return 1
  local output status
  set +e
  output="$(ssh_run_capture_with_stdin "$(remote_tmux_install_password_command)" "$password")"
  status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    [[ -n "$output" ]] && printf "%s\n" "$output"
    echo "TMUX_INSTALL_AUTH source=$source_label"
    return 0
  fi
  if [[ "$status" -eq 12 ]]; then
    return 1
  fi
  [[ -n "$output" ]] && printf "%s\n" "$output" >&2
  exit "$status"
}

try_saved_source_access_passwords() {
  PASSWORD_FILES=()
  CRED_FILES=()
  collect_wsl_source_access_credentials
  collect_ssh_config_credentials

  local file var_name password
  for file in "${PASSWORD_FILES[@]}"; do
    for var_name in SAVED_REMOTE_SUDO_PASSWORD SAVED_SSH_PASSWORD SAVED_SAMBA_PASSWORD; do
      password="$(read_saved_password_var "$file" "$var_name")"
      try_tmux_password_candidate "source-access:$var_name" "$password" && return 0
    done
  done
  for file in "${CRED_FILES[@]}"; do
    password="$(read_cred_password "$file")"
    try_tmux_password_candidate "source-access:SAMBA_CREDENTIALS_FILE" "$password" && return 0
  done
  return 1
}

install_tmux() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --sudo-password-env) SUDO_PASSWORD_ENV="${2:-}"; shift 2 ;;
      --) shift; break ;;
      *) die "Unknown install-tmux argument: $1" ;;
    esac
  done
  [[ -n "$SUDO_PASSWORD_ENV" ]] || die "--sudo-password-env must not be empty"

  local output status env_password
  set +e
  output="$(ssh_run_capture "$(remote_tmux_install_passwordless_command)")"
  status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    [[ -n "$output" ]] && printf "%s\n" "$output"
    echo "TMUX_INSTALL_AUTH source=passwordless-or-existing"
    return 0
  fi
  if [[ "$status" -ne 10 ]]; then
    [[ -n "$output" ]] && printf "%s\n" "$output" >&2
    exit "$status"
  fi

  env_password="${!SUDO_PASSWORD_ENV-}"
  try_tmux_password_candidate "env:$SUDO_PASSWORD_ENV" "$env_password" && return 0
  try_saved_source_access_passwords && return 0

  echo "REMOTE_SUDO_PASSWORD_REQUIRED env=$SUDO_PASSWORD_ENV action=install_tmux" >&2
  exit 10
}

check_channel() {
  local remote_root_q
  remote_root_q="$(single_quote "$REMOTE_ROOT")"
  ssh_run "
set -e
printf 'SSH_OK host=%s\n' '$SSH_HOST'
command -v tmux >/dev/null 2>&1 || { echo 'TMUX_MISSING install tmux on remote host' >&2; exit 127; }
printf 'TMUX_OK path=%s\n' \"\$(command -v tmux)\"
test -d $remote_root_q || { echo 'REMOTE_ROOT_MISSING $REMOTE_ROOT' >&2; exit 2; }
printf 'REMOTE_ROOT_OK path=%s\n' '$REMOTE_ROOT'
"
}

ensure_session() {
  local session_q remote_root_q state_rel_q
  session_q="$(single_quote "$SESSION_NAME")"
  remote_root_q="$(single_quote "$REMOTE_ROOT")"
  state_rel_q="$(single_quote "$STATE_DIR")"
  ssh_run "
set -e
command -v tmux >/dev/null 2>&1 || { echo 'TMUX_MISSING install tmux on remote host' >&2; exit 127; }
test -d $remote_root_q || { echo 'REMOTE_ROOT_MISSING $REMOTE_ROOT' >&2; exit 2; }
state_dir=\"\$HOME/$STATE_DIR\"
mkdir -p \"\$state_dir/commands\"
cat >\"\$state_dir/session.env\" <<EOF
SESSION_NAME=$SESSION_NAME
SSH_HOST=$SSH_HOST
REMOTE_ROOT=$REMOTE_ROOT
STATE_DIR=\$state_dir
EOF
if ! tmux has-session -t $session_q 2>/dev/null; then
  tmux new-session -d -s $session_q -c $remote_root_q
  tmux send-keys -t $session_q -l \"cd $remote_root_q\"
  tmux send-keys -t $session_q C-m
fi
echo \"SESSION_OK name=$SESSION_NAME state=\$state_dir remote=$REMOTE_ROOT\"
"
}

status_session() {
  local session_q
  session_q="$(single_quote "$SESSION_NAME")"
  ssh_run "
state_dir=\"\$HOME/$STATE_DIR\"
if tmux has-session -t $session_q 2>/dev/null; then
  echo \"SESSION_STATUS running name=$SESSION_NAME state=\$state_dir\"
else
  echo \"SESSION_STATUS stopped name=$SESSION_NAME state=\$state_dir\"
fi
if [ -f \"\$state_dir/busy\" ]; then
  printf 'BUSY '
  cat \"\$state_dir/busy\"
  echo
else
  echo 'BUSY none'
fi
if [ -L \"\$state_dir/current.log\" ] || [ -f \"\$state_dir/current.log\" ]; then
  echo \"CURRENT_LOG=\$state_dir/current.log\"
fi
"
}

stop_session() {
  local session_q
  session_q="$(single_quote "$SESSION_NAME")"
  ssh_run "
if tmux has-session -t $session_q 2>/dev/null; then
  tmux kill-session -t $session_q
  echo \"SESSION_STOPPED name=$SESSION_NAME\"
else
  echo \"SESSION_ALREADY_STOPPED name=$SESSION_NAME\"
fi
"
}

tail_log() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --command-id) COMMAND_ID="${2:-}"; shift 2 ;;
      --lines) TAIL_LINES="${2:-}"; shift 2 ;;
      --) shift; break ;;
      *) die "Unknown tail argument: $1" ;;
    esac
  done
  [[ "$TAIL_LINES" =~ ^[0-9]+$ ]] || die "--lines must be a positive integer"

  local log_path
  if [[ -n "$COMMAND_ID" ]]; then
    log_path="\$HOME/$STATE_DIR/commands/$COMMAND_ID.log"
  else
    log_path="\$HOME/$STATE_DIR/current.log"
  fi
  ssh_run "
log=$log_path
if [ ! -e \"\$log\" ]; then
  echo \"LOG_MISSING \$log\" >&2
  exit 2
fi
tail -n $TAIL_LINES \"\$log\"
"
}

run_command() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --lock) LOCK_MODE="${2:-}"; shift 2 ;;
      --no-wait) WAIT=false; shift ;;
      --command-id) COMMAND_ID="${2:-}"; shift 2 ;;
      --) shift; break ;;
      *) break ;;
    esac
  done
  [[ "$LOCK_MODE" == "none" || "$LOCK_MODE" == "exclusive" ]] || die "--lock must be none or exclusive"
  [[ $# -gt 0 ]] || die "run requires COMMAND after --"
  local user_cmd="$*"
  [[ -n "$COMMAND_ID" ]] || COMMAND_ID="$(date +%Y%m%d-%H%M%S)-$$"

  ensure_session >/dev/null

  local state_q busy_q
  state_q="$(single_quote "$(remote_state_path)")"
  busy_q="$(single_quote "$(remote_state_path)/busy")"

  if ssh_run "test -f $busy_q"; then
    echo "SESSION_BUSY name=$SESSION_NAME state=$(remote_state_path)" >&2
    exit 3
  fi

  local line_file="\$HOME/$STATE_DIR/commands/$COMMAND_ID.line"
  local log_file="\$HOME/$STATE_DIR/commands/$COMMAND_ID.log"
  local exit_file="\$HOME/$STATE_DIR/commands/$COMMAND_ID.exit"
  local lock_file="\$HOME/$STATE_DIR/project.lock"
  local remote_root_q
  remote_root_q="$(single_quote "$REMOTE_ROOT")"

  local lock_prefix=""
  local lock_suffix=""
  if [[ "$LOCK_MODE" == "exclusive" ]]; then
    lock_prefix="exec 9>\"$lock_file\"; flock 9; "
    lock_suffix="; flock -u 9"
  fi

  local command_line
  command_line="__codex_cmd_id=$(single_quote "$COMMAND_ID"); __codex_log=\"$log_file\"; __codex_exit=\"$exit_file\"; __codex_busy=\"\$HOME/$STATE_DIR/busy\"; rm -f \"\$__codex_exit\"; mkdir -p \"\$HOME/$STATE_DIR/commands\"; printf '%s remote=$REMOTE_ROOT\n' \"\$__codex_cmd_id\" > \"\$__codex_busy\"; ln -sfn \"\$__codex_log\" \"\$HOME/$STATE_DIR/current.log\"; { cd $remote_root_q; $lock_prefix{ $user_cmd; }; __codex_rc=\$?$lock_suffix; } > \"\$__codex_log\" 2>&1; printf '%s\n' \"\$__codex_rc\" > \"\$__codex_exit\"; rm -f \"\$__codex_busy\"; printf '__CODEX_CMD_DONE id=%s rc=%s\n' \"\$__codex_cmd_id\" \"\$__codex_rc\" >> \"\$__codex_log\""

  printf "%s" "$command_line" | ssh_run "cat > \"$line_file\""
  ssh_run "tmux send-keys -t $(single_quote "$SESSION_NAME") -l \"\$(cat \"$line_file\")\" && tmux send-keys -t $(single_quote "$SESSION_NAME") C-m"

  echo "COMMAND_STARTED id=$COMMAND_ID session=$SESSION_NAME log=$(remote_state_path)/commands/$COMMAND_ID.log"

  if [[ "$WAIT" == true ]]; then
    ssh_run "
exit_file=\"\$HOME/$STATE_DIR/commands/$COMMAND_ID.exit\"
log_file=\"\$HOME/$STATE_DIR/commands/$COMMAND_ID.log\"
while [ ! -f \"\$exit_file\" ]; do
  sleep 2
done
cat \"\$log_file\"
exit \"\$(cat \"\$exit_file\")\"
"
  fi
}

case "$ACTION" in
  check) check_channel ;;
  install-tmux) install_tmux "$@" ;;
  ensure) ensure_session ;;
  status) status_session ;;
  stop) stop_session ;;
  tail) tail_log "$@" ;;
  run) run_command "$@" ;;
  *) die "Unknown action: $ACTION" ;;
esac
