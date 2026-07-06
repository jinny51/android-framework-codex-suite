#!/usr/bin/env bash
set -euo pipefail
# 从本地 JSON registry + Keychain 恢复所有已记录的 SMB/Samba share root 挂载。
# 用于重启或 Codex 重启后的恢复。
#
# macOS 版差异（相对 WSL）:
# - 密码从 Keychain 读取，不是从明文 .cred / .passwords.env
# - register-project.sh 写 JSON registry，恢复必须读取同一格式

usage() {
  cat <<'USAGE_EOF'
用法:
  restore-mounts.sh [选项]

选项:
  --server NAME           仅恢复指定服务器的挂载。
  --smb-user USER         覆盖 registry 中的 SMB/Samba 用户名。
  --registry-dir PATH     Registry 目录。默认: ~/.servers/projects。
  -h, --help              显示此帮助。

输出 (每个共享一行):
  RESTORE_STATUS=mounted|already_mounted|failed|no_credentials

退出码:
  0  成功
  2  参数错误
  3  registry 目录不存在
  4  至少一个挂载失败
USAGE_EOF
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

server_filter=
smb_user_override=
registry_dir="${HOME}/.servers/projects"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server)          server_filter="${2:?缺少 --server 的值}"; shift 2 ;;
    --smb-user)        smb_user_override="${2:?缺少 --smb-user 的值}"; shift 2 ;;
    --registry-dir)    registry_dir="${2:?缺少 --registry-dir 的值}"; shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *)                 die 2 "未知参数: $1" ;;
  esac
done

[ -d "$registry_dir" ] || die 3 "registry 目录不存在: ${registry_dir}（请先执行 mount + register）"

# source 共享函数
script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$script_dir/_keychain_helpers.sh"

entries_file="$(mktemp "${TMPDIR:-/tmp}/restore-mounts.XXXXXX")"
trap 'rm -f "$entries_file"' EXIT

python3 - "$registry_dir" "$server_filter" "$smb_user_override" > "$entries_file" <<'PY'
import json
import sys
from pathlib import Path

registry_dir = Path(sys.argv[1])
server_filter = sys.argv[2]
smb_user_override = sys.argv[3]

for path in sorted(registry_dir.glob("*.json")):
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    server = str(data.get("server") or path.stem)
    if server_filter and server != server_filter:
        continue
    server_ip = str(data.get("server_ip") or server)
    default_user = smb_user_override or str(data.get("smb_user") or server)
    shares = data.get("shares") or {}
    if not isinstance(shares, dict):
        continue
    for share, item in shares.items():
        if not isinstance(item, dict):
            continue
        mount_point = str(item.get("mount_point") or "")
        if not mount_point:
            continue
        smb_user = smb_user_override or str(item.get("smb_user") or default_user)
        print("\t".join([server, server_ip, smb_user, str(share), mount_point]))
PY

mounted=0
already=0
no_credentials=0
failed=0
entries=0

while IFS=$'\t' read -r server server_ip smb_user share mount_point; do
  [ -n "$server" ] || continue
  entries=$((entries + 1))

  if mount | grep -q " on $mount_point (" 2>/dev/null; then
    echo "RESTORE_STATUS=already_mounted server=$server share=$share mount_point=$mount_point"
    already=$((already + 1))
    continue
  fi

  smb_password="$(credential_read "smb" "$smb_user" "$server_ip")"
  if [ -z "$smb_password" ] && [ "$server_ip" != "$server" ]; then
    smb_password="$(credential_read "smb" "$smb_user" "$server")"
  fi

  if [ -z "$smb_password" ]; then
    echo "RESTORE_STATUS=no_credentials server=$server share=$share mount_point=$mount_point"
    echo "WARN: Keychain 中没有 ${smb_user}@${server_ip} 的 SMB/Samba 密码；请先用 mount-share.sh --keychain 检查，必要时显式 --save-credentials 修复。" >&2
    no_credentials=$((no_credentials + 1))
    continue
  fi

  mkdir -p "$mount_point" 2>/dev/null || true
  mount_url="//${smb_user}:${smb_password}@${server_ip}/${share}"

  if mount -t smbfs "$mount_url" "$mount_point" 2>/dev/null; then
    echo "RESTORE_STATUS=mounted server=$server share=$share mount_point=$mount_point"
    mounted=$((mounted + 1))
  else
    echo "RESTORE_STATUS=failed server=$server share=$share mount_point=$mount_point"
    hash="$(account_key "$smb_user" "$server_ip" 2>/dev/null || echo "")"
    if [ -n "$hash" ]; then
      env_file="$(keychain_env_path "$hash")"
      keychain_env_set "$env_file" "SMB_PASSWORD_STATE" "failed" 2>/dev/null || true
    fi
    failed=$((failed + 1))
  fi
done < "$entries_file"

echo "RESTORE_SUMMARY mounted=$mounted already_mounted=$already no_credentials=$no_credentials failed=$failed entries=$entries"
[ "$failed" -eq 0 ] || exit 4
