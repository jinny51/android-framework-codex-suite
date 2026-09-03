#!/usr/bin/env bash
# ── Keychain 凭据模型共享函数 ──
# 被其他脚本 source 使用，不直接执行。
#
# 安全须知:
#   security add-generic-password -w <password> 让密码短暂出现在进程参数中。
#   调用方必须:
#    - 不在 set -x / 日志中打印密码
#    - 不在 shell history 中记录（set +o history）
#    - 用完后立即 unset 密码变量

_keychain_helpers_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_keychain_atomic_state="$(cd "$_keychain_helpers_dir/../../../lib" && pwd)/akbs_plugin_state/atomic.py"

atomic_state_write_private() {
  local file="$1"
  python3 "$_keychain_atomic_state" write --path "$file" --mode 600
}

atomic_state_update_env() {
  python3 "$_keychain_atomic_state" update-env "$@"
}

# 计算 account_key = sha256("<remote-user>@<server>")
account_key() {
  local user="$1" server="$2"
  printf "%s@%s" "$user" "$server" | shasum -a 256 | awk '{print $1}'
}

# 构建 Keychain service name
keychain_service() {
  local role="$1" hash="$2"
  printf "codex.android-mac-source-access.%s.%s" "$role" "$hash"
}

# .keychain.env 文件路径
keychain_env_path() {
  local hash="$1"
  local dir="${CODEX_CREDENTIALS_DIR:-$HOME/.servers/credentials}"
  printf "%s/%s.keychain.env" "$dir" "$hash"
}

# local.keychain.env 文件路径
local_keychain_env_path() {
  local dir="${CODEX_CREDENTIALS_DIR:-$HOME/.servers/credentials}"
  printf "%s/local.keychain.env" "$dir"
}

# 安全存储密码到 Keychain
# 注意: macOS security CLI 不支持 stdin 传密码（-w - 无效），
# 只能用 -w <password> 传参。调用方必须确保不暴露密码。
keychain_store() {
  local service="$1" account="$2" password="$3"
  security add-generic-password \
    -s "$service" \
    -a "$account" \
    -w "$password" \
    -U 2>/dev/null
}

# 从 Keychain 读取密码
keychain_read() {
  local service="$1" account="$2"
  security find-generic-password \
    -s "$service" \
    -a "$account" \
    -w 2>/dev/null || true
}

# 删除 Keychain 中的密码
keychain_delete() {
  local service="$1" account="$2"
  security delete-generic-password \
    -s "$service" \
    -a "$account" 2>/dev/null || true
}

# 检查密码状态
keychain_check() {
  local service="$1" account="$2"
  if security find-generic-password \
    -s "$service" \
    -a "$account" \
    -w >/dev/null 2>&1; then
    printf "stored"
  else
    printf "missing"
  fi
}

# 更新 .keychain.env 中的字段
keychain_env_set() {
  local file="$1" key="$2" value="$3"
  [ -f "$file" ] || return 0
  atomic_state_update_env --path "$file" --mode 600 --set "$key=$value"
}

password_state_key() {
  case "$1" in
    ssh) printf "SSH_PASSWORD_STATE" ;;
    smb) printf "SMB_PASSWORD_STATE" ;;
    remote-sudo) printf "REMOTE_SUDO_PASSWORD_STATE" ;;
    *) return 1 ;;
  esac
}

# 保存密码到 Keychain 并更新 .keychain.env
# 调用方必须在调用后 unset 密码变量
credential_save() {
  local role="$1" password="$2" remote_user="$3" server="$4"
  local hash service

  hash=$(account_key "$remote_user" "$server")
  service=$(keychain_service "$role" "$hash")

  # 写入 Keychain
  keychain_store "$service" "${remote_user}@${server}" "$password"

  # 更新 .keychain.env
  local env_file
  env_file=$(keychain_env_path "$hash")
  local credential_dir
  credential_dir=$(dirname "$env_file")
  mkdir -p "$credential_dir"
  chmod 700 "$credential_dir"
  local state_key
  state_key=$(password_state_key "$role")
  local updated_at
  updated_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  atomic_state_update_env \
    --path "$env_file" \
    --mode 600 \
    --default "ACCOUNT_KEY=${hash}" \
    --default "REMOTE_USER=${remote_user}" \
    --default "SERVER=${server}" \
    --default "SSH_KEYCHAIN_SERVICE=$(keychain_service "ssh" "$hash")" \
    --default "SMB_KEYCHAIN_SERVICE=$(keychain_service "smb" "$hash")" \
    --default "REMOTE_SUDO_KEYCHAIN_SERVICE=$(keychain_service "remote-sudo" "$hash")" \
    --default "SSH_PASSWORD_STATE=missing" \
    --default "SMB_PASSWORD_STATE=missing" \
    --default "REMOTE_SUDO_PASSWORD_STATE=missing" \
    --default "UPDATED_AT=${updated_at}" \
    --set "${state_key}=stored" \
    --set "UPDATED_AT=${updated_at}"
  chmod 600 "$env_file"
}

# 从 Keychain 读取密码（带 fallback 链）
# 优先级: 显式环境变量 > Keychain
credential_read() {
  local role="$1" remote_user="$2" server="$3"
  local hash service account password

  hash=$(account_key "$remote_user" "$server")
  service=$(keychain_service "$role" "$hash")
  account="${remote_user}@${server}"

  # 1. 尝试 Keychain
  password=$(keychain_read "$service" "$account")

  # 2. 如果 Keychain 没有，检查显式环境变量
  if [ -z "$password" ]; then
    local explicit_var="CODEX_$(printf '%s' "$role" | tr '[:lower:]-' '[:upper:]_')_PASSWORD"
    if [ -n "${!explicit_var:-}" ]; then
      password="${!explicit_var}"
    fi
  fi

  printf '%s' "$password"
}

# 保存本机 sudo 密码到 Keychain
local_credential_save() {
  local password="$1" local_user="${2:-$(whoami)}"
  local hash service

  hash=$(printf "%s@localhost" "$local_user" | shasum -a 256 | awk '{print $1}')
  service=$(keychain_service "local" "$hash")

  keychain_store "$service" "${local_user}@localhost" "$password"

  local env_file
  env_file=$(local_keychain_env_path)
  local credential_dir
  credential_dir=$(dirname "$env_file")
  mkdir -p "$credential_dir"
  chmod 700 "$credential_dir"
  cat <<-EOF | atomic_state_write_private "$env_file"
LOCAL_USER=${local_user}
LOCAL_USER_HASH=${hash}
LOCAL_SUDO_KEYCHAIN_SERVICE=${service}
LOCAL_SUDO_PASSWORD_STATE=stored
UPDATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
  chmod 600 "$env_file"
}

# 读取本机 sudo 密码
local_credential_read() {
  local local_user="${1:-$(whoami)}"
  local hash service

  hash=$(printf "%s@localhost" "$local_user" | shasum -a 256 | awk '{print $1}')
  service=$(keychain_service "local" "$hash")

  keychain_read "$service" "${local_user}@localhost"
}
