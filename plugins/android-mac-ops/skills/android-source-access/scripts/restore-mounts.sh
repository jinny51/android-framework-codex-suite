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
import re
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
            remote_share_root = str(item.get("remote_path") or "")
            transport = str(item.get("mount_transport") or "smbfs")
            if transport != "smbfs":
                raise ValueError(f"{path}: share {share!r} 不是 smbfs transport")
            if not remote_share_root.startswith("/"):
                raise ValueError(f"{path}: share {share!r} 缺少绝对 remote_path")
            projects = item.get("projects")
            if not isinstance(projects, dict) or not projects:
                raise ValueError(f"{path}: share {share!r} 缺少已登记 remote project facts")
            project_ids = []
            remote_roots = []
            for project_name, project in sorted(projects.items()):
                if not isinstance(project, dict):
                    raise ValueError(f"{path}: project {project_name!r} 必须是对象")
                remote_root = str(project.get("remote_root") or project.get("remote_path") or "")
                ssh_host = str(project.get("ssh_host") or server)
                platform = str(project.get("platform") or "")
                bridge = expand_home_path(str(project.get("artifact_bridge_path") or project.get("local_path") or ""))
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(project_name)).strip("-._")
                expected_id = f"{platform.lower()}-{safe_name}"
                actual_id = str(project.get("project_id") or expected_id)
                if str(project.get("identity_schema") or data.get("identity_schema") or "android-remote-project-identity-v1") != "android-remote-project-identity-v1":
                    raise ValueError(f"{path}: project {project_name!r} identity schema 不支持")
                if ssh_host != server or actual_id != expected_id:
                    raise ValueError(f"{path}: project {project_name!r} identity 与 platform/project 不一致")
                if not remote_root.startswith("/") or not (remote_root == remote_share_root or remote_root.startswith(remote_share_root.rstrip("/") + "/")):
                    raise ValueError(f"{path}: project {project_name!r} remote_root 不在 share remote_path 下")
                if platform not in {"rk", "mtk", "unisoc"}:
                    raise ValueError(f"{path}: project {project_name!r} platform 无效")
                if not (bridge == mount_point or bridge.startswith(mount_point.rstrip("/") + "/")):
                    raise ValueError(f"{path}: project {project_name!r} artifact bridge 不在 mount_point 下")
                project_ids.append(actual_id)
                remote_roots.append(remote_root)
            path_parts = smb_path.split("/")
            if any(not part or part in {".", ".."} for part in path_parts):
                raise ValueError(f"{path}: share {share!r} 的 smb_path 非法")
            values = (
                server,
                server_ip,
                smb_user,
                str(share),
                smb_path,
                mount_point,
                ",".join(project_ids),
                ",".join(remote_roots),
                remote_share_root,
                transport,
            )
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

while IFS=$'\t' read -r server server_ip smb_user share smb_path mount_point project_ids remote_roots remote_share_root transport; do
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
        echo "RESTORE_STATUS=already_mounted server=$server share=$share mount_point=$mount_point project_ids=$project_ids remote_roots=$remote_roots transport=$transport source_verified=true"
        already=$((already + 1))
        ;;
      *)
        echo "RESTORE_STATUS=mounted server=$server share=$share mount_point=$mount_point project_ids=$project_ids remote_roots=$remote_roots transport=$transport source_verified=true"
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
