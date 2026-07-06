#!/usr/bin/env bash
set -euo pipefail
# 检查 macOS Keychain 中密码的存储状态。

usage() {
  cat <<'USAGE'
用法:
  keychain-check.sh --role smb --remote-user test55 --server 192.168.100.6

选项:
  --role ROLE           ssh | smb | remote-sudo | local。必需。
  --remote-user USER   远端 SSH 用户名。
  --server HOST        服务器 IP 或主机名。
  --local-user USER    本机用户名。默认: $(whoami)。
  -h, --help           显示此帮助。

输出:
  KEYCHAIN_STATUS=stored | missing

退出码:
  0  成功
  2  参数错误
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

role=; remote_user=; server=; local_user=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --role)        role="${2:?}"; shift 2 ;;
    --remote-user) remote_user="${2:?}"; shift 2 ;;
    --server)      server="${2:?}"; shift 2 ;;
    --local-user)  local_user="${2:?}"; shift 2 ;;
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
    status=$(keychain_check "$service" "${remote_user}@${server}")
    echo "KEYCHAIN_STATUS=$status"
    echo "KEYCHAIN_SERVICE=$service"
    echo "KEYCHAIN_ACCOUNT=${remote_user}@${server}"
    ;;
  local)
    local_user="${local_user:-$(whoami)}"
    hash=$(printf "%s@localhost" "$local_user" | shasum -a 256 | awk '{print $1}')
    service=$(keychain_service "local" "$hash")
    status=$(keychain_check "$service" "${local_user}@localhost")
    echo "KEYCHAIN_STATUS=$status"
    echo "KEYCHAIN_SERVICE=$service"
    echo "KEYCHAIN_ACCOUNT=${local_user}@localhost"
    ;;
  *) die 2 "不支持的 role: $role" ;;
esac
