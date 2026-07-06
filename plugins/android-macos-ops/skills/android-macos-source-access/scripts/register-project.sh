#!/usr/bin/env bash
set -euo pipefail
# 将检测到的 Android 项目注册到本地 JSON registry。
# Registry 路径: ~/.servers/projects/<server>.json

usage() {
  cat <<'USAGE'
用法:
  register-project.sh --server 名称 --server-ip IP --share 名称 \
    --mount-point 路径 --remote-share-path 路径 \
    --project 名称 --project-path 路径 --platform 名称 \
    --remote-project-path 路径 [选项]

选项:
  --server NAME               SSH 主机别名。必需。
  --server-ip IP              服务器 IP。必需。
  --smb-user USER             SMB/Samba 用户名。默认: server 名称。
  --share NAME                Samba 共享名。必需。
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

server=; server_ip=; smb_user=; share=; mount_point=; remote_share_path=
project=; project_path=; platform=; remote_project_path=
registry_dir="${HOME}/.servers/projects"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server)               server="${2:?缺少 --server 的值}"; shift 2 ;;
    --server-ip)            server_ip="${2:?缺少 --server-ip 的值}"; shift 2 ;;
    --smb-user)             smb_user="${2:?缺少 --smb-user 的值}"; shift 2 ;;
    --share)                share="${2:?缺少 --share 的值}"; shift 2 ;;
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
smb_user="${smb_user:-$server}"

case "$platform" in
  unisoc|mtk|rk) ;;
  *) die 3 "不支持的平台 '$platform'；预期: unisoc, mtk, rk" ;;
esac

mkdir -p "$registry_dir"
chmod 700 "$registry_dir"

registry_file="$registry_dir/${server}.json"
status="created"
[ -f "$registry_file" ] && status="updated"

python3 - "$registry_file" "$server" "$server_ip" "$smb_user" "$share" "$mount_point" \
  "$remote_share_path" "$project" "$project_path" "$platform" "$remote_project_path" <<'PY'
import json, sys, os

f, srv, ip, smb_user, sh, mp, rsp, proj, pp, plat, rpp = sys.argv[1:]

data = {}
if os.path.exists(f):
    with open(f) as fh:
        data = json.load(fh)

data["server"] = srv
data["server_ip"] = ip
data["smb_user"] = smb_user
data.setdefault("shares", {}).setdefault(sh, {
    "mount_point": mp,
    "remote_path": rsp,
    "smb_user": smb_user,
    "projects": {}
})
data["shares"][sh]["mount_point"] = mp
data["shares"][sh]["remote_path"] = rsp
data["shares"][sh]["smb_user"] = smb_user
data["shares"][sh]["projects"][proj] = {
    "platform": plat,
    "local_path": pp,
    "remote_path": rpp
}

with open(f, "w") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY

chmod 600 "$registry_file"

echo "REGISTRY_FILE=$registry_file"
echo "REGISTRY_STATUS=$status"
echo "PROJECT=$project"
echo "PLATFORM=$platform"
echo "SSH_HOST=$server"
echo "REMOTE_ROOT=$remote_project_path"
