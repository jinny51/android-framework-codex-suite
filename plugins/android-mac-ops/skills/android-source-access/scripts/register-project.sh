#!/usr/bin/env bash
set -euo pipefail
# 将检测到的 Android 项目注册到本地 JSON registry。
# Registry 路径: ~/.servers/projects/<server>.json

usage() {
  cat <<'USAGE'
用法:
  register-project.sh --server 名称 --server-ip IP --share 名称 \
    [--smb-path 路径] \
    --mount-point 路径 --remote-share-path 路径 \
    --project 名称 --project-path 路径 --platform 名称 \
    --remote-project-path 路径 [选项]

选项:
  --server NAME               SSH 主机别名。必需。
  --server-ip IP              服务器 IP。必需。
  --smb-user USER             SMB/Samba 用户名。默认: server 名称。
  --share NAME                Registry 中的稳定挂载项名称。必需。
  --smb-path PATH             服务器上的 SMB 路径，可含 share 下的子路径。
                              默认与 --share 相同。
  --mount-point PATH          本地共享挂载点。必需。
  --remote-share-path PATH    远端共享路径，如 /home/test61/unisoc。必需。
  --project NAME              项目/SDK 名称。必需。
  --project-path PATH         本地项目路径。必需。
  --platform NAME             平台: unisoc, mtk, rk。必需。
  --remote-project-path PATH  远端项目路径。必需。
  --registry-dir PATH         Registry 目录。默认: ~/.servers/projects。
  -h, --help                  显示此帮助。

输出:
  REGISTRY_FILE              文件路径。
  REGISTRY_STATUS            created | updated。
  PROJECT                    项目名。
  PLATFORM                   平台。
  SSH_HOST                   SSH 主机。
  REMOTE_ROOT                远端路径。

退出码:
  0  成功
  2  缺少参数
  3  平台名非法
USAGE
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

server=; server_ip=; smb_user=; share=; smb_path=; mount_point=; remote_share_path=
project=; project_path=; platform=; remote_project_path=
registry_dir="${HOME}/.servers/projects"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server)               server="${2:?缺少 --server 的值}"; shift 2 ;;
    --server-ip)            server_ip="${2:?缺少 --server-ip 的值}"; shift 2 ;;
    --smb-user)             smb_user="${2:?缺少 --smb-user 的值}"; shift 2 ;;
    --share)                share="${2:?缺少 --share 的值}"; shift 2 ;;
    --smb-path)             smb_path="${2:?缺少 --smb-path 的值}"; shift 2 ;;
    --mount-point)          mount_point="${2:?缺少 --mount-point 的值}"; shift 2 ;;
    --remote-share-path)    remote_share_path="${2:?缺少 --remote-share-path 的值}"; shift 2 ;;
    --project)              project="${2:?缺少 --project 的值}"; shift 2 ;;
    --project-path)         project_path="${2:?缺少 --project-path 的值}"; shift 2 ;;
    --platform)             platform="${2:?缺少 --platform 的值}"; shift 2 ;;
    --remote-project-path)  remote_project_path="${2:?缺少 --remote-project-path 的值}"; shift 2 ;;
    --registry-dir)         registry_dir="${2:?缺少 --registry-dir 的值}"; shift 2 ;;
    -h|--help)              usage; exit 0 ;;
    *)                      die 2 "未知参数: $1" ;;
  esac
done

[ -n "$server" ]              || die 2 "--server 是必需的"
[ -n "$server_ip" ]           || die 2 "--server-ip 是必需的"
[ -n "$share" ]               || die 2 "--share 是必需的"
[ -n "$project" ]             || die 2 "--project 是必需的"
[ -n "$platform" ]            || die 2 "--platform 是必需的"
[ -n "$project_path" ]        || die 2 "--project-path 是必需的"
[ -n "$remote_project_path" ] || die 2 "--remote-project-path 是必需的"
[ -n "$remote_share_path" ]   || die 2 "--remote-share-path 是必需的"
case "$remote_share_path" in /*) ;; *) die 2 "--remote-share-path 必须是绝对路径" ;; esac
case "$remote_project_path" in
  "$remote_share_path"|"$remote_share_path"/*) ;;
  *) die 2 "--remote-project-path 必须等于或位于 --remote-share-path 下" ;;
esac
smb_user="${smb_user:-$server}"
smb_path="${smb_path:-$share}"

case "$server" in
  *[!A-Za-z0-9._-]*) die 2 "--server 只能包含字母、数字、点、下划线和连字符" ;;
esac
case "$share" in
  ""|*/*) die 2 "--share 必须是稳定的单段注册项名称，不能包含路径分隔符" ;;
esac
case "/$smb_path/" in
  *"//"*|*"/./"*|*"/../"*)
    die 2 "--smb-path 必须是相对服务器的 SMB 路径，且不能包含空段、. 或 .."
    ;;
esac

work_root="${ANDROID_WORK_ROOT:-$HOME/work}"
case "$mount_point" in
  "$work_root"|"$work_root"/*) ;;
  *) die 2 "--mount-point 必须位于 Android work root 下: ${work_root}" ;;
esac
case "$project_path" in
  "$mount_point"|"$mount_point"/*) ;;
  *) die 2 "--project-path 必须位于共享挂载点下: ${mount_point}" ;;
esac

case "$platform" in
  unisoc|mtk|rk) ;;
  *) die 3 "不支持的平台 '$platform'；预期: unisoc, mtk, rk" ;;
esac

mkdir -p "$registry_dir"
chmod 700 "$registry_dir"

registry_file="$registry_dir/${server}.json"
plugin_lib="$(cd "$(dirname "$0")/../../../lib" && pwd)"

status="$(PYTHONPATH="$plugin_lib${PYTHONPATH:+:$PYTHONPATH}" python3 - "$registry_file" "$server" "$server_ip" "$smb_user" "$share" "$smb_path" "$mount_point" \
  "$remote_share_path" "$project" "$project_path" "$platform" "$remote_project_path" <<'PY'
import os
import re
import sys
from pathlib import Path

from akbs_plugin_state.atomic import update_json

f, srv, ip, smb_user, sh, smb_path, mp, rsp, proj, pp, plat, rpp = sys.argv[1:]
identity_schema = "android-remote-project-identity-v1"
project_id = f"{plat.lower()}-{re.sub(r'[^A-Za-z0-9._-]+', '-', proj).strip('-._')}"


def portable_home_path(value):
    home = os.path.expanduser("~").rstrip("/")
    if value == home:
        return "$HOME"
    if home and value.startswith(home + "/"):
        return "$HOME/" + value[len(home) + 1 :]
    return value

def update_registry(data):
    data["server"] = srv
    data["server_ip"] = ip
    data["smb_user"] = smb_user
    data["identity_schema"] = identity_schema
    data.setdefault("shares", {}).setdefault(sh, {
        "mount_point": mp,
        "remote_path": rsp,
        "smb_user": smb_user,
        "projects": {}
    })
    data["shares"][sh]["mount_point"] = mp
    data["shares"][sh]["smb_path"] = smb_path
    data["shares"][sh]["remote_path"] = rsp
    data["shares"][sh]["smb_user"] = smb_user
    data["shares"][sh]["mount_transport"] = "smbfs"
    data["shares"][sh]["projects"][proj] = {
        "identity_schema": identity_schema,
        "project_id": project_id,
        "ssh_host": srv,
        "platform": plat,
        "local_path": portable_home_path(pp),
        "artifact_bridge_path": portable_home_path(pp),
        "mount_transport": "smbfs",
        "remote_path": rpp,
        "remote_root": rpp,
    }
    data["shares"][sh]["mount_point"] = portable_home_path(mp)


existed = update_json(Path(f), update_registry)
print("updated" if existed else "created")
PY
)"

chmod 600 "$registry_file"

echo "REGISTRY_FILE=$registry_file"
echo "REGISTRY_STATUS=$status"
echo "SMB_PATH=$smb_path"
echo "PROJECT=$project"
echo "PLATFORM=$platform"
echo "SSH_HOST=$server"
echo "REMOTE_ROOT=$remote_project_path"
echo "PROJECT_IDENTITY_SCHEMA=android-remote-project-identity-v1"
python3 - "$platform" "$project" <<'PY'
import re
import sys
print("PROJECT_ID=" + sys.argv[1].lower() + "-" + re.sub(r"[^A-Za-z0-9._-]+", "-", sys.argv[2]).strip("-._"))
PY
echo "MOUNT_TRANSPORT=smbfs"
echo "ARTIFACT_BRIDGE_PATH=$project_path"
