#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
restore-project-mount.sh --project /local/repo/path --remember-current [options]
restore-project-mount.sh --project /local/repo/path --restore [options]
restore-project-mount.sh --list [options]

Remember or restore an already-mounted WSL/CIFS Android project path.
Use this for reboot recovery after the initial project mount has already been
created by android-source-access.

Required:
  --project PATH       Local WSL project path to remember or restore.

Modes:
  --remember-current   Record the current mount for --project.
  --restore            Restore the exact remembered project path after reboot.
  --list               List remembered project mounts without restoring.

Optional:
  --user USER          Samba username; overrides the remembered username on restore.
  --password PASS      Samba password. Prefer SAMBA_PASSWORD env to avoid shell history.
  --remember-password  With --remember-current, store Samba credentials locally with mode 600.
  --ssh-host HOST      With --remember-current, remember the remote SSH host for this project.
  --remote-root PATH   With --remember-current, remember the remote source path for this project.
  --platform NAME      With --remember-current, remember platform such as unisoc, mtk, or rk.
  --sdk-name NAME      With --remember-current, remember the SDK/project directory name.
  --uid UID            Owner uid for mounted files. Default: invoking user uid.
  --gid GID            Owner gid for mounted files. Default: invoking user gid.
  --vers VERSION       CIFS version to try first. Default: remembered value or 3.0.
  --local-sudo-password-env NAME
                       Environment variable containing local WSL sudo password
                       for non-interactive restore. Optional.
  --registry-dir PATH  Local registry dir. Default: $HOME/.servers/projects.
  --credentials-dir PATH
                       Local credentials dir. Default: $HOME/.servers/credentials.

Environment:
  SAMBA_PASSWORD       Samba password if --password is omitted.

Run from WSL. If not root, the script uses sudo for restore.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

PROJECT_PATH=""
SMB_USER=""
SMB_PASSWORD="${SAMBA_PASSWORD:-}"
LOCAL_UID="$(id -u)"
LOCAL_GID="$(id -g)"
PREFERRED_VERS=""
LOCAL_SUDO_PASSWORD_ENV=""
REMOTE_SSH_HOST=""
REMOTE_ROOT=""
PLATFORM=""
SDK_NAME=""
RESTORE=false
REMEMBER_CURRENT=false
LIST=false
REMEMBER_PASSWORD=false
REGISTRY_DIR="$HOME/.servers/projects"
CREDENTIALS_DIR="$HOME/.servers/credentials"
PROJECT_IDENTITY_SCHEMA="android-remote-project-identity-v1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATOMIC_STATE="$(cd "$SCRIPT_DIR/../../../lib" && pwd)/akbs_plugin_state/atomic.py"

atomic_state_write_private() {
  local file="$1"
  python3 "$ATOMIC_STATE" write --path "$file" --mode 600
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_PATH="${2:-}"; shift 2 ;;
    --user) SMB_USER="${2:-}"; shift 2 ;;
    --password) SMB_PASSWORD="${2:-}"; shift 2 ;;
    --remember-password) REMEMBER_PASSWORD=true; shift ;;
    --ssh-host) REMOTE_SSH_HOST="${2:-}"; shift 2 ;;
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --platform) PLATFORM="${2:-}"; shift 2 ;;
    --sdk-name) SDK_NAME="${2:-}"; shift 2 ;;
    --uid) LOCAL_UID="${2:-}"; shift 2 ;;
    --gid) LOCAL_GID="${2:-}"; shift 2 ;;
    --vers) PREFERRED_VERS="${2:-}"; shift 2 ;;
    --local-sudo-password-env) LOCAL_SUDO_PASSWORD_ENV="${2:-}"; shift 2 ;;
    --restore) RESTORE=true; shift ;;
    --remember-current) REMEMBER_CURRENT=true; shift ;;
    --list) LIST=true; shift ;;
    --registry-dir) REGISTRY_DIR="${2:-}"; shift 2 ;;
    --credentials-dir) CREDENTIALS_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

mode_count=0
[[ "$REMEMBER_CURRENT" == true ]] && mode_count=$((mode_count + 1))
[[ "$RESTORE" == true ]] && mode_count=$((mode_count + 1))
[[ "$LIST" == true ]] && mode_count=$((mode_count + 1))
if [[ "$mode_count" -ne 1 ]]; then
  die "choose exactly one mode: --remember-current, --restore, or --list"
fi
if [[ "$LIST" == false ]]; then
  [[ -n "$PROJECT_PATH" ]] || die "--project is required"
  [[ "$PROJECT_PATH" == /* ]] || die "--project must be an absolute WSL path"
fi
if [[ "$REMEMBER_PASSWORD" == true && "$REMEMBER_CURRENT" != true ]]; then
  die "--remember-password is only valid with --remember-current"
fi

account_key_for_user_share() {
  local user="$1"
  local share="$2"
  local share_body server
  share_body="${share#//}"
  server="${share_body%%/*}"
  [[ -n "$user" && -n "$server" ]] || die "cannot derive Samba account key from user/share"
  printf "%s@%s" "$user" "$server" | sha256sum | awk '{print $1}'
}

server_for_share() {
  local share="$1"
  local share_body
  share_body="${share#//}"
  printf "%s" "${share_body%%/*}"
}

registry_file_for_account() {
  local user="$1"
  local share="$2"
  local key
  key="$(account_key_for_user_share "$user" "$share")"
  printf "%s/%s.env" "$REGISTRY_DIR" "$key"
}

credentials_file_for_account() {
  local user="$1"
  local share="$2"
  local key
  key="$(account_key_for_user_share "$user" "$share")"
  printf "%s/%s.cred" "$CREDENTIALS_DIR" "$key"
}

passwords_file_for_account() {
  local user="$1"
  local share="$2"
  local key
  key="$(account_key_for_user_share "$user" "$share")"
  printf "%s/%s.passwords.env" "$CREDENTIALS_DIR" "$key"
}

local_sudo_password_file() {
  printf "%s/local-sudo.env" "$CREDENTIALS_DIR"
}

load_saved_passwords() {
  local file="$1"
  SAVED_SSH_PASSWORD=""
  SAVED_SAMBA_PASSWORD=""
  SAVED_REMOTE_SUDO_PASSWORD=""
  SAVED_LOCAL_SUDO_PASSWORD=""
  if [[ -f "$file" ]]; then
    # shellcheck disable=SC1090
    source "$file"
  fi
}

load_saved_local_sudo_password() {
  local file="$1"
  SAVED_LOCAL_SUDO_PASSWORD=""
  if [[ -f "$file" ]]; then
    # shellcheck disable=SC1090
    source "$file"
  fi
}

print_array_assignment() {
  local name="$1"
  shift
  printf "%s=(" "$name"
  local value
  for value in "$@"; do
    printf " %q" "$value"
  done
  printf " )\n"
}

project_id_for() {
  local platform="$1" sdk_name="$2" safe_name
  case "$platform" in unisoc|mtk|rk) ;; *) return 1 ;; esac
  safe_name="$(printf "%s" "$sdk_name" | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
  [[ -n "$safe_name" ]] || return 1
  printf "%s-%s" "$platform" "$safe_name"
}

registered_mount_source() {
  local source target fstype rel
  source="$(findmnt -T "$PROJECT_PATH" -n -o SOURCE 2>/dev/null || true)"
  target="$(findmnt -T "$PROJECT_PATH" -n -o TARGET 2>/dev/null || true)"
  fstype="$(findmnt -T "$PROJECT_PATH" -n -o FSTYPE 2>/dev/null || true)"
  case "$fstype" in cifs|smb3) ;; *) return 1 ;; esac
  [[ -n "$source" && -n "$target" && "$source" == //* ]] || return 1
  rel="${PROJECT_PATH#"$target"}"
  rel="${rel#/}"
  [[ -z "$rel" ]] || source="${source%/}/$rel"
  printf "%s" "$source"
}

remember_current_mount() {
  [[ -n "$REMOTE_SSH_HOST" ]] || die "--ssh-host is required with --remember-current"
  [[ "$REMOTE_ROOT" == /* ]] || die "--remote-root must be absolute with --remember-current"
  case "$PLATFORM" in unisoc|mtk|rk) ;; *) die "--platform must be unisoc, mtk, or rk with --remember-current" ;; esac
  [[ -n "$SDK_NAME" ]] || die "--sdk-name is required with --remember-current"

  local source target fstype options rel project_share registry_file mount_user vers credentials_file existing_credentials old_project_path old_smb_user old_vers samba_server
  local old_remote_ssh_host old_remote_root old_platform old_sdk_name project_id
  local -a paths shares versions ssh_hosts remote_roots platforms sdk_names project_ids identity_schemas mount_transports artifact_bridge_paths
  source="$(findmnt -T "$PROJECT_PATH" -n -o SOURCE 2>/dev/null || true)"
  target="$(findmnt -T "$PROJECT_PATH" -n -o TARGET 2>/dev/null || true)"
  fstype="$(findmnt -T "$PROJECT_PATH" -n -o FSTYPE 2>/dev/null || true)"
  options="$(findmnt -T "$PROJECT_PATH" -n -o OPTIONS 2>/dev/null || true)"

  [[ -n "$source" && -n "$target" ]] || die "no mount found for project: $PROJECT_PATH"
  [[ "$source" == //* || "$fstype" == cifs || "$fstype" == smb3 ]] || die "project is not on a Samba/CIFS source: $source"
  project_id="$(project_id_for "$PLATFORM" "$SDK_NAME")" || die "cannot derive neutral project identity"

  mount_user="$(printf "%s" "$options" | tr ',' '\n' | awk -F= '$1=="username"{print $2; exit}')"
  SMB_USER="${SMB_USER:-$mount_user}"
  vers="$(printf "%s" "$options" | tr ',' '\n' | awk -F= '$1=="vers"{print $2; exit}')"
  PREFERRED_VERS="${PREFERRED_VERS:-${vers:-3.0}}"

  rel="${PROJECT_PATH#"$target"}"
  rel="${rel#/}"
  project_share="$source"
  if [[ -n "$rel" ]]; then
    project_share="${source%/}/$rel"
  fi

  mkdir -p "$REGISTRY_DIR"
  registry_file="$(registry_file_for_account "$SMB_USER" "$project_share")"
  samba_server="$(server_for_share "$project_share")"
  command -v flock >/dev/null 2>&1 || die "flock is required to update remembered mount state safely"
  local transaction_lock="${registry_file}.transaction.lock"
  exec 8>"$transaction_lock"
  chmod 600 "$transaction_lock"
  flock 8

  existing_credentials=""
  if [[ -f "$registry_file" ]]; then
    old_project_path="$PROJECT_PATH"
    old_smb_user="$SMB_USER"
    old_vers="$PREFERRED_VERS"
    SAMBA_CREDENTIALS_FILE=""
    PROJECT_PATHS=()
    SAMBA_PROJECT_SHARES=()
    PREFERRED_VERS_LIST=()
    REMOTE_SSH_HOSTS=()
    REMOTE_ROOTS=()
    PLATFORMS=()
    SDK_NAMES=()
    PROJECT_IDS=()
    PROJECT_IDENTITY_SCHEMAS=()
    MOUNT_TRANSPORTS=()
    ARTIFACT_BRIDGE_PATHS=()
    # shellcheck disable=SC1090
    source "$registry_file"
    existing_credentials="${SAMBA_CREDENTIALS_FILE:-}"
    if declare -p PROJECT_PATHS >/dev/null 2>&1; then
      paths=("${PROJECT_PATHS[@]}")
    fi
    if declare -p SAMBA_PROJECT_SHARES >/dev/null 2>&1; then
      shares=("${SAMBA_PROJECT_SHARES[@]}")
    fi
    if declare -p PREFERRED_VERS_LIST >/dev/null 2>&1; then
      versions=("${PREFERRED_VERS_LIST[@]}")
    fi
    if declare -p REMOTE_SSH_HOSTS >/dev/null 2>&1; then
      ssh_hosts=("${REMOTE_SSH_HOSTS[@]}")
    fi
    if declare -p REMOTE_ROOTS >/dev/null 2>&1; then
      remote_roots=("${REMOTE_ROOTS[@]}")
    fi
    if declare -p PLATFORMS >/dev/null 2>&1; then
      platforms=("${PLATFORMS[@]}")
    fi
    if declare -p SDK_NAMES >/dev/null 2>&1; then
      sdk_names=("${SDK_NAMES[@]}")
    fi
    if declare -p PROJECT_IDS >/dev/null 2>&1; then project_ids=("${PROJECT_IDS[@]}"); fi
    if declare -p PROJECT_IDENTITY_SCHEMAS >/dev/null 2>&1; then identity_schemas=("${PROJECT_IDENTITY_SCHEMAS[@]}"); fi
    if declare -p MOUNT_TRANSPORTS >/dev/null 2>&1; then mount_transports=("${MOUNT_TRANSPORTS[@]}"); fi
    if declare -p ARTIFACT_BRIDGE_PATHS >/dev/null 2>&1; then artifact_bridge_paths=("${ARTIFACT_BRIDGE_PATHS[@]}"); fi
    for i in "${!paths[@]}"; do
      ssh_hosts[$i]="${ssh_hosts[$i]:-}"
      remote_roots[$i]="${remote_roots[$i]:-}"
      platforms[$i]="${platforms[$i]:-}"
      sdk_names[$i]="${sdk_names[$i]:-}"
      shares[$i]="${shares[$i]:-}"
      versions[$i]="${versions[$i]:-3.0}"
      project_ids[$i]="${project_ids[$i]:-}"
      identity_schemas[$i]="${identity_schemas[$i]:-$PROJECT_IDENTITY_SCHEMA}"
      mount_transports[$i]="${mount_transports[$i]:-cifs}"
      artifact_bridge_paths[$i]="${artifact_bridge_paths[$i]:-${paths[$i]}}"
    done
    old_remote_ssh_host="$REMOTE_SSH_HOST"
    old_remote_root="$REMOTE_ROOT"
    old_platform="$PLATFORM"
    old_sdk_name="$SDK_NAME"
    PROJECT_PATH="$old_project_path"
    SMB_USER="$old_smb_user"
    PREFERRED_VERS="$old_vers"
    REMOTE_SSH_HOST="$old_remote_ssh_host"
    REMOTE_ROOT="$old_remote_root"
    PLATFORM="$old_platform"
    SDK_NAME="$old_sdk_name"
  fi
  credentials_file="$existing_credentials"

  if [[ "$REMEMBER_PASSWORD" == true ]]; then
    [[ -n "${SMB_USER:-}" ]] || die "Samba username is required to remember credentials"
    [[ -n "$SMB_PASSWORD" ]] || die "Samba password is required via SAMBA_PASSWORD or --password with --remember-password"
    mkdir -p "$CREDENTIALS_DIR"
    chmod 700 "$CREDENTIALS_DIR"
    credentials_file="$(credentials_file_for_account "$SMB_USER" "$project_share")"
    echo "NOTICE: storing Samba credentials locally at $credentials_file" >&2
    {
      printf "username=%s\n" "$SMB_USER"
      printf "password=%s\n" "$SMB_PASSWORD"
    } | atomic_state_write_private "$credentials_file"
    chmod 600 "$credentials_file"
  fi

  local found_index=-1 i
  for i in "${!paths[@]}"; do
    if [[ "${paths[$i]}" == "$PROJECT_PATH" ]]; then
      found_index="$i"
      break
    fi
  done
  if [[ "$found_index" -ge 0 ]]; then
    shares[$found_index]="$project_share"
    versions[$found_index]="$PREFERRED_VERS"
    ssh_hosts[$found_index]="${REMOTE_SSH_HOST:-${ssh_hosts[$found_index]:-}}"
    remote_roots[$found_index]="${REMOTE_ROOT:-${remote_roots[$found_index]:-}}"
    platforms[$found_index]="${PLATFORM:-${platforms[$found_index]:-}}"
    sdk_names[$found_index]="${SDK_NAME:-${sdk_names[$found_index]:-}}"
    project_ids[$found_index]="$project_id"
    identity_schemas[$found_index]="$PROJECT_IDENTITY_SCHEMA"
    mount_transports[$found_index]="cifs"
    artifact_bridge_paths[$found_index]="$PROJECT_PATH"
  else
    paths+=("$PROJECT_PATH")
    shares+=("$project_share")
    versions+=("$PREFERRED_VERS")
    ssh_hosts+=("${REMOTE_SSH_HOST:-}")
    remote_roots+=("${REMOTE_ROOT:-}")
    platforms+=("${PLATFORM:-}")
    sdk_names+=("${SDK_NAME:-}")
    project_ids+=("$project_id")
    identity_schemas+=("$PROJECT_IDENTITY_SCHEMA")
    mount_transports+=("cifs")
    artifact_bridge_paths+=("$PROJECT_PATH")
  fi

  {
    printf "SAMBA_SERVER=%q\n" "$samba_server"
    printf "SAMBA_USER=%q\n" "${SMB_USER:-}"
    if [[ -n "$credentials_file" && -f "$credentials_file" ]]; then
      printf "SAMBA_CREDENTIALS_FILE=%q\n" "$credentials_file"
    fi
    print_array_assignment PROJECT_PATHS "${paths[@]}"
    print_array_assignment SAMBA_PROJECT_SHARES "${shares[@]}"
    print_array_assignment PREFERRED_VERS_LIST "${versions[@]}"
    print_array_assignment REMOTE_SSH_HOSTS "${ssh_hosts[@]}"
    print_array_assignment REMOTE_ROOTS "${remote_roots[@]}"
    print_array_assignment PLATFORMS "${platforms[@]}"
    print_array_assignment SDK_NAMES "${sdk_names[@]}"
    print_array_assignment PROJECT_IDS "${project_ids[@]}"
    print_array_assignment PROJECT_IDENTITY_SCHEMAS "${identity_schemas[@]}"
    print_array_assignment MOUNT_TRANSPORTS "${mount_transports[@]}"
    print_array_assignment ARTIFACT_BRIDGE_PATHS "${artifact_bridge_paths[@]}"
  } | atomic_state_write_private "$registry_file"
  chmod 600 "$registry_file"

  if [[ -n "$credentials_file" && -f "$credentials_file" ]]; then
    echo "REMEMBER_OK project=$PROJECT_PATH project_id=$project_id registry=$registry_file credentials=stored credentials_file=$credentials_file"
  else
    echo "REMEMBER_OK project=$PROJECT_PATH project_id=$project_id registry=$registry_file credentials=not_stored"
  fi
}

restore_project_mount() {
  local registry_file share remembered_user remembered_vers requested_vers remembered_credentials cred_file base_opts versions vers last_err using_temp_cred credential_state file i found passwords_file local_sudo_file account_level_local_sudo_password saved_local_sudo_password
  local remembered_ssh_host remembered_remote_root remembered_platform remembered_sdk_name remembered_project_id remembered_identity_schema remembered_transport remembered_bridge expected_project_id actual_source
  requested_vers="$PREFERRED_VERS"
  found=false
  shopt -s nullglob
  for file in "$REGISTRY_DIR"/*.env; do
    PROJECT_PATHS=()
    SAMBA_PROJECT_SHARES=()
    PREFERRED_VERS_LIST=()
    REMOTE_SSH_HOSTS=()
    REMOTE_ROOTS=()
    PLATFORMS=()
    SDK_NAMES=()
    PROJECT_IDS=()
    PROJECT_IDENTITY_SCHEMAS=()
    MOUNT_TRANSPORTS=()
    ARTIFACT_BRIDGE_PATHS=()
    SAMBA_USER=""
    SAMBA_CREDENTIALS_FILE=""
    # shellcheck disable=SC1090
    source "$file"
    for i in "${!PROJECT_PATHS[@]}"; do
      if [[ "${PROJECT_PATHS[$i]}" == "$PROJECT_PATH" ]]; then
        registry_file="$file"
        share="${SAMBA_PROJECT_SHARES[$i]:-}"
        remembered_user="${SAMBA_USER:-}"
        remembered_vers="${PREFERRED_VERS_LIST[$i]:-3.0}"
        remembered_credentials="${SAMBA_CREDENTIALS_FILE:-}"
        remembered_ssh_host="${REMOTE_SSH_HOSTS[$i]:-}"
        remembered_remote_root="${REMOTE_ROOTS[$i]:-}"
        remembered_platform="${PLATFORMS[$i]:-}"
        remembered_sdk_name="${SDK_NAMES[$i]:-}"
        remembered_project_id="${PROJECT_IDS[$i]:-}"
        remembered_identity_schema="${PROJECT_IDENTITY_SCHEMAS[$i]:-$PROJECT_IDENTITY_SCHEMA}"
        remembered_transport="${MOUNT_TRANSPORTS[$i]:-cifs}"
        remembered_bridge="${ARTIFACT_BRIDGE_PATHS[$i]:-${PROJECT_PATHS[$i]}}"
        found=true
        break 2
      fi
    done
  done
  shopt -u nullglob
  [[ "$found" == true ]] || die "no remembered mount for project: $PROJECT_PATH"

  SMB_USER="${SMB_USER:-$remembered_user}"
  PREFERRED_VERS="${requested_vers:-$remembered_vers}"

  [[ -n "$share" ]] || die "remembered mount is missing SAMBA_PROJECT_SHARE: $registry_file"
  [[ -n "$remembered_ssh_host" ]] || die "remembered mount is missing REMOTE_SSH_HOST: $registry_file"
  [[ "$remembered_remote_root" == /* ]] || die "remembered mount has invalid REMOTE_ROOT: $registry_file"
  case "$remembered_platform" in unisoc|mtk|rk) ;; *) die "remembered mount has invalid PLATFORM: $registry_file" ;; esac
  [[ -n "$remembered_sdk_name" ]] || die "remembered mount is missing SDK_NAME: $registry_file"
  [[ "$remembered_identity_schema" == "$PROJECT_IDENTITY_SCHEMA" ]] || die "remembered mount has unsupported project identity schema: $remembered_identity_schema"
  [[ "$remembered_transport" == cifs ]] || die "remembered mount has invalid transport: $remembered_transport"
  [[ "$remembered_bridge" == "$PROJECT_PATH" ]] || die "remembered artifact bridge path does not match requested project: $remembered_bridge"
  expected_project_id="$(project_id_for "$remembered_platform" "$remembered_sdk_name")" || die "cannot derive remembered project identity"
  [[ -n "$remembered_project_id" ]] || remembered_project_id="$expected_project_id"
  [[ "$remembered_project_id" == "$expected_project_id" ]] || die "remembered project identity does not match SSH_HOST/REMOTE_ROOT"

  actual_source="$(registered_mount_source || true)"
  if [[ -n "$actual_source" ]]; then
    [[ "$actual_source" == "$share" ]] || die "project is mounted from unexpected CIFS source: actual=$actual_source expected=$share"
    echo "MOUNT_OK project=$PROJECT_PATH project_id=$remembered_project_id already_mounted=true source_verified=true"
    return 0
  fi
  passwords_file="$(passwords_file_for_account "$SMB_USER" "$share")"
  load_saved_passwords "$passwords_file"
  account_level_local_sudo_password="$SAVED_LOCAL_SUDO_PASSWORD"
  local_sudo_file="$(local_sudo_password_file)"
  load_saved_local_sudo_password "$local_sudo_file"
  if [[ -z "$SMB_PASSWORD" && -n "$SAVED_SAMBA_PASSWORD" ]]; then
    SMB_PASSWORD="$SAVED_SAMBA_PASSWORD"
  fi
  saved_local_sudo_password="${SAVED_LOCAL_SUDO_PASSWORD:-$account_level_local_sudo_password}"

  if [[ -n "$remembered_credentials" && -f "$remembered_credentials" ]]; then
    cred_file="$remembered_credentials"
  else
    [[ -n "$SMB_USER" ]] || die "Samba username is missing; rerun with --user"
    [[ -n "$SMB_PASSWORD" ]] || die "Samba password is required via SAMBA_PASSWORD or --password, or remember Samba credentials with --remember-password"
  fi

  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    sudo_args=(--project "$PROJECT_PATH" --restore
      --uid "$LOCAL_UID" --gid "$LOCAL_GID" --vers "$PREFERRED_VERS"
      --registry-dir "$REGISTRY_DIR" --credentials-dir "$CREDENTIALS_DIR")
    if [[ -n "$SMB_USER" ]]; then
      sudo_args+=(--user "$SMB_USER")
    fi
    if sudo -n true 2>/dev/null; then
      exec sudo -n env SAMBA_PASSWORD="$SMB_PASSWORD" "$0" "${sudo_args[@]}"
    fi
    if [[ -n "$LOCAL_SUDO_PASSWORD_ENV" && -n "${!LOCAL_SUDO_PASSWORD_ENV:-}" ]]; then
      exec sudo -S -p '' env SAMBA_PASSWORD="$SMB_PASSWORD" "$0" "${sudo_args[@]}" <<<"${!LOCAL_SUDO_PASSWORD_ENV}"
    fi
    if [[ -n "$saved_local_sudo_password" ]]; then
      exec sudo -S -p '' env SAMBA_PASSWORD="$SMB_PASSWORD" "$0" "${sudo_args[@]}" <<<"$saved_local_sudo_password"
    fi
    exec sudo env SAMBA_PASSWORD="$SMB_PASSWORD" "$0" "${sudo_args[@]}"
  fi

  command -v mount.cifs >/dev/null 2>&1 || die "mount.cifs not found. Install cifs-utils in WSL first."

  if [[ -e "$PROJECT_PATH" && ! -d "$PROJECT_PATH" ]]; then
    die "project mount target exists but is not a directory: $PROJECT_PATH"
  fi
  mkdir -p "$PROJECT_PATH"

  if mountpoint -q "$PROJECT_PATH"; then
    die "project path is mounted but its CIFS source could not be verified: $PROJECT_PATH"
  fi

  if [[ -n "$(find "$PROJECT_PATH" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    die "project mount target is non-empty but not usable: $PROJECT_PATH"
  fi

  using_temp_cred=false
  if [[ -z "${cred_file:-}" ]]; then
    cred_file="$(mktemp /tmp/codex-samba-cred.XXXXXX)"
    using_temp_cred=true
    trap "rm -f '$cred_file'" EXIT
    chmod 600 "$cred_file"
    {
      printf "username=%s\n" "$SMB_USER"
      printf "password=%s\n" "$SMB_PASSWORD"
    } >"$cred_file"
  fi

  base_opts="credentials=$cred_file,iocharset=utf8,uid=$LOCAL_UID,gid=$LOCAL_GID,file_mode=0644,dir_mode=0755,noperm,noserverino"
  versions=("$PREFERRED_VERS" "3.0" "2.1" "2.0")
  last_err=""

  for vers in "${versions[@]}"; do
    [[ -n "$vers" ]] || continue
    if mount -t cifs "$share" "$PROJECT_PATH" -o "$base_opts,vers=$vers" 2>/tmp/codex-source-cifs-mount.err; then
      actual_source="$(registered_mount_source || true)"
      if [[ "$actual_source" == "$share" ]]; then
        if [[ "$using_temp_cred" == true ]]; then credential_state=temp; else credential_state=stored; fi
        echo "MOUNT_OK project=$PROJECT_PATH project_id=$remembered_project_id vers=$vers credentials=$credential_state source_verified=true"
        return 0
      fi
      umount "$PROJECT_PATH" 2>/dev/null || true
      last_err="mounted source verification failed: actual=${actual_source:-missing} expected=$share"
      continue
    fi
    last_err="$(tail -n 3 /tmp/codex-source-cifs-mount.err 2>/dev/null || true)"
  done

  die "restore failed for project=$PROJECT_PATH. ${last_err:-No detail available.}"
}

list_remembered_mounts() {
  if [[ ! -d "$REGISTRY_DIR" ]]; then
    echo "NO_REMEMBERED_PROJECTS registry=$REGISTRY_DIR"
    return 0
  fi

  local found=false file project share user credentials credentials_state ssh_host remote_root platform sdk_name project_id transport bridge i
  shopt -s nullglob
  for file in "$REGISTRY_DIR"/*.env; do
    found=true
    PROJECT_PATHS=()
    SAMBA_PROJECT_SHARES=()
    PREFERRED_VERS_LIST=()
    REMOTE_SSH_HOSTS=()
    REMOTE_ROOTS=()
    PLATFORMS=()
    SDK_NAMES=()
    PROJECT_IDS=()
    MOUNT_TRANSPORTS=()
    ARTIFACT_BRIDGE_PATHS=()
    SAMBA_USER=""
    SAMBA_CREDENTIALS_FILE=""
    # shellcheck disable=SC1090
    source "$file"
    user="${SAMBA_USER:-}"
    credentials="${SAMBA_CREDENTIALS_FILE:-}"
    if [[ -n "$credentials" && -f "$credentials" ]]; then
      credentials_state="stored"
    else
      credentials_state="not_stored"
    fi
    for i in "${!PROJECT_PATHS[@]}"; do
      project="${PROJECT_PATHS[$i]}"
      share="${SAMBA_PROJECT_SHARES[$i]:-}"
      ssh_host="${REMOTE_SSH_HOSTS[$i]:-}"
      remote_root="${REMOTE_ROOTS[$i]:-}"
      platform="${PLATFORMS[$i]:-}"
      sdk_name="${SDK_NAMES[$i]:-}"
      project_id="${PROJECT_IDS[$i]:-}"
      transport="${MOUNT_TRANSPORTS[$i]:-cifs}"
      bridge="${ARTIFACT_BRIDGE_PATHS[$i]:-$project}"
      if [[ "$credentials_state" == stored ]]; then
        echo "REMEMBERED_PROJECT project=$project project_id=$project_id share=$share user=$user ssh_host=$ssh_host remote_root=$remote_root platform=$platform sdk_name=$sdk_name transport=$transport artifact_bridge=$bridge credentials=stored credentials_file=$credentials registry=$file"
      else
        echo "REMEMBERED_PROJECT project=$project project_id=$project_id share=$share user=$user ssh_host=$ssh_host remote_root=$remote_root platform=$platform sdk_name=$sdk_name transport=$transport artifact_bridge=$bridge credentials=not_stored registry=$file"
      fi
    done
  done
  shopt -u nullglob

  if [[ "$found" == false ]]; then
    echo "NO_REMEMBERED_PROJECTS registry=$REGISTRY_DIR"
  fi
}

if [[ "$LIST" == true ]]; then
  list_remembered_mounts
elif [[ "$REMEMBER_CURRENT" == true ]]; then
  remember_current_mount
else
  restore_project_mount
fi
