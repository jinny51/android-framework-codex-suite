#!/usr/bin/env bash
set -euo pipefail
# macOS Keychain 密码保存工具。
#
# 安全策略:
#   密码从环境变量 CODEX_TARGET_PASSWORD 读取，不经过命令行参数。
#   如果 CODEX_TARGET_PASSWORD 未设置，从 stdin 读取。

usage() {
  cat <<'USAGE'
用法:
  export CODEX_TARGET_PASSWORD='secret'
  keychain-store.sh --role smb --remote-user test55 --server 192.168.100.6
  unset CODEX_TARGET_PASSWORD

  或从 stdin:
  printf '%s' "$password" | keychain-store.sh --role smb --remote-user test55 --server 192.168.100.6

选项:
  --role ROLE           ssh | smb | remote-sudo | local。必需。
  --remote-user USER   远端 SSH 用户名。local 角色不需要。
  --server HOST        服务器 IP 或主机名。local 角色不需要。
  --local-user USER    本机用户名。默认: $(whoami)。仅 local 角色使用。
  -h, --help           显示此帮助。

输出:
  KEYCHAIN_STATUS=stored
  KEYCHAIN_SERVICE=<service name>

退出码:
  0  成功
  2  参数错误
  3  密码为空
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

# 获取密码：优先环境变量，其次 stdin
password="${CODEX_TARGET_PASSWORD:-}"
if [ -z "$password" ]; then
  password=$(cat 2>/dev/null || true)
fi
[ -n "$password" ] || die 3 "密码为空。请设置 CODEX_TARGET_PASSWORD 或通过 stdin 传入。"

source "$(cd "$(dirname "$0")" && pwd)/_keychain_helpers.sh"

case "$role" in
  ssh|smb|remote-sudo)
    [ -n "$remote_user" ] || die 2 "--remote-user 是必需的"
    [ -n "$server" ] || die 2 "--server 是必需的"
    credential_save "$role" "$password" "$remote_user" "$server"
    hash=$(account_key "$remote_user" "$server")
    service=$(keychain_service "$role" "$hash")
    echo "KEYCHAIN_STATUS=stored"
    echo "KEYCHAIN_SERVICE=$service"
    echo "KEYCHAIN_ACCOUNT=${remote_user}@${server}"
    ;;
  local)
    local_user="${local_user:-$(whoami)}"
    local_credential_save "$password" "$local_user"
    echo "KEYCHAIN_STATUS=stored"
    echo "KEYCHAIN_SERVICE=$(keychain_service 'local' "$(printf '%s@localhost' "$local_user" | shasum -a 256 | awk '{print $1}')")"
    echo "KEYCHAIN_ACCOUNT=${local_user}@localhost"
    ;;
  *) die 2 "不支持的 role: $role" ;;
esac
