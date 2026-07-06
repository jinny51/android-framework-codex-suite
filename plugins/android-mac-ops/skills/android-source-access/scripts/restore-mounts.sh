#!/usr/bin/env bash
set -euo pipefail
# 从本地 registry + Keychain 恢复所有已记录的项目挂载。
# 用于重启或 Codex 重启后的恢复。
#
# macOS 版差异（相对 WSL）:
# - 密码从 Keychain 读取，不是从明文 .cred / .passwords.env
# - 使用 .keychain.env 作为 Keychain 引用

usage() {
  cat <<'USAGE_EOF'
用法:
  restore-mounts.sh [选项]

选项:
  --server NAME           仅恢复指定服务器的挂载。
  --registry-dir PATH     Registry 目录。默认: ~/.servers/projects。
  --credentials-dir PATH  凭据引用目录。默认: ~/.servers/credentials。
  -h, --help              显示此帮助。

输出 (每个共享一行):
  RESTORE_STATUS=mounted|already_mounted|failed|no_credentials

退出码:
  0  成功
  2  参数错误
  3  registry 目录不存在
USAGE_EOF
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

server_filter=
registry_dir="${HOME}/.servers/projects"
credentials_dir="${HOME}/.servers/credentials"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server)          server_filter="${2:?缺少 --server 的值}"; shift 2 ;;
    --registry-dir)    registry_dir="${2:?缺少 --registry-dir 的值}"; shift 2 ;;
    --credentials-dir) credentials_dir="${2:?缺少 --credentials-dir 的值}"; shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *)                 die 2 "未知参数: $1" ;;
  esac
done

[ -d "$registry_dir" ] || die 3 "registry 目录不存在: ${registry_dir}（请先执行 mount + register）"

# source 共享函数
script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$script_dir/_keychain_helpers.sh"

find "$registry_dir" -name '*.env' -maxdepth 1 | while IFS= read -r reg_file; do
  [ -f "$reg_file" ] || continue
  server="$(basename "$reg_file" .env)"
  [ -n "$server_filter" ] && [ "$server" != "$server_filter" ] && continue

  # shellcheck disable=SC1090
  source "$reg_file"

  SAMBA_USER="${SAMBA_USER:-$server}"
  SAMBA_SERVER="${SAMBA_SERVER:-}"
  ACCOUNT_KEY="${ACCOUNT_KEY:-}"
  SMB_KEYCHAIN_SERVICE="${SMB_KEYCHAIN_SERVICE:-}"

  if [ -z "$SAMBA_SERVER" ]; then
    echo "RESTORE_STATUS=no_server_info server=$server"
    continue
  fi

  # 从 Keychain 读取 SMB 密码
  smb_password=""
  if [ -n "$SMB_KEYCHAIN_SERVICE" ] && [ -n "$SAMBA_USER" ]; then
    smb_password="$(keychain_read "$SMB_KEYCHAIN_SERVICE" "${SAMBA_USER}@${SAMBA_SERVER}")"
  elif [ -n "$ACCOUNT_KEY" ] && [ -n "$SAMBA_USER" ]; then
    # 兼容旧版：通过 account_key 反推 service
    fallback_service="$(keychain_service "smb" "$ACCOUNT_KEY")"
    smb_password="$(keychain_read "$fallback_service" "${SAMBA_USER}@${SAMBA_SERVER}")"
  fi

  if [ -z "$smb_password" ]; then
    echo "RESTORE_STATUS=no_credentials server=$server"
    # 尝试无密码挂载 guest 模式
    for i in "${!PROJECT_PATHS[@]}"; do
      mp="${PROJECT_PATHS[$i]}"
      share_url="${SAMBA_SHARES[$i]:-}"
      if [ -n "$share_url" ] && [ ! -d "$mp/build" ] && [ ! -d "$mp/.repo" ]; then
        # 只能用 smbutil 验证
        echo "WARN: 无法恢复 $mp（Keychain 中无密码）" >&2
      fi
    done
    continue
  fi

  # 遍历项目路径
  for i in "${!PROJECT_PATHS[@]}"; do
    mp="${PROJECT_PATHS[$i]}"
    share_url="${SAMBA_SHARES[$i]:-}"

    if [ -z "$share_url" ]; then
      echo "RESTORE_STATUS=no_share_url server=$server"
      continue
    fi

    # 检查是否已挂载
    if mount | grep -q " on $mp (" 2>/dev/null; then
      echo "RESTORE_STATUS=already_mounted server=$server path=$mp"
      continue
    fi

    # 挂载
    mkdir -p "$mp" 2>/dev/null || true
    share_body="${share_url#//}"
    mount_url="//${SAMBA_USER}:${smb_password}@${share_body}"

    if mount -t smbfs "$mount_url" "$mp" 2>/dev/null; then
      echo "RESTORE_STATUS=mounted server=$server path=$mp"
    else
      echo "RESTORE_STATUS=failed server=$server path=$mp"
      # 更新 Keychain 状态
      if [ -n "$ACCOUNT_KEY" ]; then
        env_file="$(keychain_env_path "$ACCOUNT_KEY")"
        keychain_env_set "$env_file" "SMB_PASSWORD_STATE" "failed" 2>/dev/null || true
      fi
    fi
  done
done

echo "RESTORE_SUMMARY OK"
