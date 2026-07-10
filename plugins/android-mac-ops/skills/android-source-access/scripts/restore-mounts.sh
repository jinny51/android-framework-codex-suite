#!/usr/bin/env bash
set -euo pipefail
# 从 register-project.sh 写入的 JSON registry 恢复 SMB/Samba share 挂载。

usage() {
  cat <<'USAGE'
用法:
  restore-mounts.sh [选项]

选项:
  --server NAME          仅恢复指定服务器的挂载。
  --smb-user USER        覆盖 registry 中的 SMB/Samba 用户名。
  --registry-dir PATH    Registry 目录。默认: ~/.servers/projects。
  -h, --help             显示此帮助。

输出:
  RESTORE_STATUS=mounted|already_mounted|failed|no_credentials
  RESTORE_SUMMARY mounted=N already_mounted=N no_credentials=N failed=N entries=N

退出码:
  0  所有匹配项均已挂载或原本已挂载
  1  没有匹配的 JSON registry 项
  2  参数或 registry 内容错误
  3  registry 目录不存在
  4  至少一个挂载失败
  5  至少一个挂载缺少 Keychain 凭据
USAGE
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
    --server)       server_filter="${2:?缺少 --server 的值}"; shift 2 ;;
    --smb-user)     smb_user_override="${2:?缺少 --smb-user 的值}"; shift 2 ;;
    --registry-dir) registry_dir="${2:?缺少 --registry-dir 的值}"; shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *)              die 2 "未知参数: $1" ;;
  esac
done

[ -d "$registry_dir" ] || die 3 "registry 目录不存在: ${registry_dir}（请先执行 mount + register）"

script_dir="$(cd "$(dirname "$0")" && pwd)"
entries_file="$(mktemp "${TMPDIR:-/tmp}/android-mac-restore.XXXXXX")"
trap 'rm -f "$entries_file"' EXIT

if ! python3 - "$registry_dir" "$server_filter" "$smb_user_override" > "$entries_file" <<'PY'
import json
import sys
from pathlib import Path

registry_dir = Path(sys.argv[1])
server_filter = sys.argv[2]
smb_user_override = sys.argv[3]


def expand_home_path(value):
    home = str(Path.home())
    for marker in ("$HOME", "${HOME}", "~"):
        if value == marker:
            return home
        prefix = marker + "/"
        if value.startswith(prefix):
            return str(Path(home) / value[len(prefix):])
    return value

try:
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
            raise ValueError(f"{path}: shares 必须是对象")
        for share, item in sorted(shares.items()):
            if not isinstance(item, dict):
                raise ValueError(f"{path}: share {share!r} 必须是对象")
            mount_point = expand_home_path(str(item.get("mount_point") or ""))
            smb_path = str(item.get("smb_path") or share)
            smb_user = smb_user_override or str(item.get("smb_user") or default_user)
            path_parts = smb_path.split("/")
            if any(not part or part in {".", ".."} for part in path_parts):
                raise ValueError(f"{path}: share {share!r} 的 smb_path 非法")
            values = (server, server_ip, smb_user, str(share), smb_path, mount_point)
            if not all(values):
                raise ValueError(f"{path}: share {share!r} 缺少恢复字段")
            if any("\t" in value or "\n" in value for value in values):
                raise ValueError(f"{path}: 恢复字段包含非法换行或制表符")
            print("\t".join(values))
except (OSError, ValueError, json.JSONDecodeError) as exc:
    print(f"ERROR: 无法读取 JSON registry: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
then
  exit 2
fi

mounted=0
already=0
no_credentials=0
failed=0
entries=0

while IFS=$'\t' read -r server server_ip smb_user share smb_path mount_point; do
  [ -n "$server" ] || continue
  entries=$((entries + 1))

  if mount_output="$(
    "$script_dir/mount-share.sh" \
      --share "//${server_ip}/${smb_path}" \
      --mount-point "$mount_point" \
      --user "$smb_user" \
      --remote-user "$smb_user" \
      --server "$server_ip" \
      --keychain \
      --non-interactive 2>&1
  )"; then
    case "$mount_output" in
      *MOUNT_STATUS=already_mounted*)
        echo "RESTORE_STATUS=already_mounted server=$server share=$share mount_point=$mount_point"
        already=$((already + 1))
        ;;
      *)
        echo "RESTORE_STATUS=mounted server=$server share=$share mount_point=$mount_point"
        mounted=$((mounted + 1))
        ;;
    esac
  else
    status=$?
    if [ "$status" -eq 5 ]; then
      echo "RESTORE_STATUS=no_credentials server=$server share=$share mount_point=$mount_point"
      echo "WARN: Keychain 中没有 ${smb_user}@${server_ip} 的 SMB/Samba 密码" >&2
      no_credentials=$((no_credentials + 1))
    else
      echo "RESTORE_STATUS=failed server=$server share=$share mount_point=$mount_point"
      echo "WARN: ${mount_output}" >&2
      failed=$((failed + 1))
    fi
  fi
done < "$entries_file"

echo "RESTORE_SUMMARY mounted=$mounted already_mounted=$already no_credentials=$no_credentials failed=$failed entries=$entries"

[ "$entries" -gt 0 ] || exit 1
[ "$failed" -eq 0 ] || exit 4
[ "$no_credentials" -eq 0 ] || exit 5
