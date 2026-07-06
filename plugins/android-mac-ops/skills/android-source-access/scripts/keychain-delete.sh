#!/usr/bin/env bash
set -euo pipefail
# 从 macOS Keychain 删除密码，并更新 .keychain.env 状态。

usage() {
  cat <<'USAGE'
用法:
  keychain-delete.sh --role smb --remote-user test55 --server 192.168.100.6
  keychain-delete.sh --role local

选项:
  --role ROLE           ssh | smb | remote-sudo | local。必需。
  --remote-user USER   远端 SSH 用户名。
  --server HOST        服务器 IP 或主机名。
  --local-user USER    本机用户名。默认: $(whoami)。
  --all                删除该角色对应的完整 .keychain.env（仅远端角色）。
  -h, --help           显示此帮助。

输出:
  KEYCHAIN_STATUS=deleted | not_found

退出码:
  0  成功
  2  参数错误
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

role=; remote_user=; server=; local_user=; remove_all=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --role)        role="${2:?}"; shift 2 ;;
    --remote-user) remote_user="${2:?}"; shift 2 ;;
    --server)      server="${2:?}"; shift 2 ;;
    --local-user)  local_user="${2:?}"; shift 2 ;;
    --all)         remove_all=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$role" ] || die 2 "--role 是必需的"

source "$(cd "$(dirname "$0")" && pwd)/_keychain_helpers.sh"

case "$role" in
  ssh|smb|remote-sudo)
    [ -n "$remote_user" ] || die 2 "--remote-user 是必需的"
    [ -n "$server" ] || die 2 "--server 是必需的"
    hash=$(account_key "$remote_user" "$server")
    service=$(keychain_service "$role" "$hash")
    keychain_delete "$service" "${remote_user}@${server}"

    env_file=$(keychain_env_path "$hash")
    keychain_env_set "$env_file" "${role^^}_PASSWORD_STATE" "missing"
    keychain_env_set "$env_file" "UPDATED_AT" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    if [ "$remove_all" = true ]; then
      rm -f "$env_file"
      rm -f "$(project_registry_path "$hash")"
    fi
    echo "KEYCHAIN_STATUS=deleted"
    ;;
  local)
    local_user="${local_user:-$(whoami)}"
    hash=$(printf "%s@localhost" "$local_user" | shasum -a 256 | awk '{print $1}')
    service=$(keychain_service "local" "$hash")
    keychain_delete "$service" "${local_user}@localhost"
    rm -f "$(local_keychain_env_path)"
    echo "KEYCHAIN_STATUS=deleted"
    ;;
  *) die 2 "不支持的 role: $role" ;;
esac
