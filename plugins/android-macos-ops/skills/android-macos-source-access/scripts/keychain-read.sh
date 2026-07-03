#!/usr/bin/env bash
set -euo pipefail
# 从 macOS Keychain 读取已存储的密码。

usage() {
  cat <<'USAGE'
用法:
  keychain-read.sh --role smb --remote-user test55 --server 192.168.100.6

选项:
  --role ROLE           ssh | smb | remote-sudo | local。必需。
  --remote-user USER   远端 SSH 用户名。local 角色不需要。
  --server HOST        服务器 IP 或主机名。local 角色不需要。
  --local-user USER    本机用户名。默认: $(whoami)。仅 local 角色使用。
  -h, --help           显示此帮助。

输出:
  密码内容到 stdout。无密码时输出空字符串。

退出码:
  0  成功（密码存在或不存在都是 0，用 --check 确认状态）
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
    credential_read "$role" "$remote_user" "$server"
    ;;
  local)
    local_user="${local_user:-$(whoami)}"
    local_credential_read "$local_user"
    ;;
  *) die 2 "不支持的 role: $role" ;;
esac
