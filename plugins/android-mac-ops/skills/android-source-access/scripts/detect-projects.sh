#!/usr/bin/env bash
set -euo pipefail
# 扫描已挂载的 Samba 共享目录树，识别 Android 源码项目。
# 平台和 SDK 名称通过 SSH 远端源码检测解析，逻辑与 WSL inspect-android-sdk.sh 一致。
#
# 项目名解析优先级（与 WSL 一致）：
#   1. 关键仓库 git branch（frameworks/base, device/sprd, vendor/sprd, kernel）
#      排除: master, main, develop, dev, release, stable, android-*
#   2. BRANCH_BUILDTYPE（平台 device/vendor .mk 文件）
#   3. SDK_NAME_REQUIRED — 需用户提供

usage() {
  cat <<'USAGE'
用法:
  detect-projects.sh --mount-point /挂载/共享/路径 [选项]

选项:
  --mount-point PATH       已挂载的 Samba 共享根目录。必需。
  --ssh-host HOST          远端 SSH 主机（用于源码检测项目名/平台）。建议提供。
  --remote-share-path PATH 远端共享路径，如 /home/test61/unisoc。建议提供。
  --max-depth N            扫描深度上限。默认: 2。
  -h, --help               显示此帮助。

输出 (每个项目一个块):
  PROJECT_NAME             项目/SDK 名称。
  PROJECT_PATH             本地完整路径。
  PROJECT_NAME_SOURCE      名称来源: project_branch | BRANCH_BUILDTYPE | none。
  PLATFORM                 unisoc | mtk | rk | unknown。
  REMOTE_ROOT              远端项目路径。

检测规则:
  - 包含 .repo/ 或 (build/ + frameworks/) 的目录视为 Android 项目。
  - 平台: vendor/sprd 或 device/sprd → unisoc
          vendor/mediatek → mtk
          device/rockchip → rk

退出码:
  0  成功
  1  未检测到项目
  2  缺少参数
  3  挂载点不存在
USAGE
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

mount_point=
ssh_host=
remote_share_path=
max_depth=2

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mount-point)        mount_point="${2:?缺少 --mount-point 的值}"; shift 2 ;;
    --ssh-host)           ssh_host="${2:?缺少 --ssh-host 的值}"; shift 2 ;;
    --remote-share-path)  remote_share_path="${2:?缺少 --remote-share-path 的值}"; shift 2 ;;
    --max-depth)          max_depth="${2:?缺少 --max-depth 的值}"; shift 2 ;;
    -h|--help)            usage; exit 0 ;;
    *)                    die 2 "未知参数: $1" ;;
  esac
done

[ -n "$mount_point" ] || die 2 "--mount-point 是必需的"
[ -d "$mount_point" ] || die 3 "挂载点不存在: $mount_point"
case "$max_depth" in
  ''|*[!0-9]*) die 2 "--max-depth 必须是非负整数" ;;
esac

# ── 辅助函数 ──
is_android_project() {
  local dir="$1"
  [ -d "$dir/.repo" ] && return 0
  [ -d "$dir/build" ] && [ -d "$dir/frameworks" ] && return 0
  return 1
}

# ── SSH 远端检测（与 WSL inspect-android-sdk.sh 逻辑一致）──
inspect_remote() {
  local remote_root="$1"
  [ -n "$ssh_host" ] || { echo "SDK_NAME_REQUIRED"; echo "no_ssh_host" >&2; return; }
  local script_dir remote_inspector remote_command
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  remote_inspector="$script_dir/../../../lib/android_source_access/remote_inspector.sh"
  [ -r "$remote_inspector" ] || {
    echo "remote SDK inspector is missing: $remote_inspector" >&2
    return 3
  }
  remote_command="bash -s -- $(printf '%q' "$remote_root") '' '' 0 0 discovery"
  ssh \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 \
    "$ssh_host" \
    "$remote_command" \
    <"$remote_inspector"
}

# BSD find 不支持 -maxdepth/-mindepth；用 Python 做本地有界遍历。
list_local_directories() {
  python3 - "$mount_point" "$max_depth" <<'PY'
import os
import sys

root = os.path.abspath(sys.argv[1])
max_depth = int(sys.argv[2])

for current, directories, _files in os.walk(root):
    directories.sort()
    relative = os.path.relpath(current, root)
    depth = 0 if relative == "." else relative.count(os.sep) + 1
    if depth >= max_depth:
        directories[:] = []
    sys.stdout.buffer.write(os.fsencode(current) + b"\0")
PY
}

# ── 扫描项目目录 ──
found=0
while IFS= read -r -d '' dir; do
  if is_android_project "$dir"; then
    dir_name="$(basename "$dir")"
    remote_root="${remote_share_path:-}/$dir_name"

    if [ -n "$ssh_host" ] && [ -n "$remote_share_path" ]; then
      inspect_result="$(inspect_remote "$remote_root" 2>/dev/null)" || true
      if [ -n "$inspect_result" ]; then
        eval "$inspect_result"
        SDK_SOURCE="${SOURCE_SDK_SOURCE:-none}"
        BRANCH_BUILDTYPE=""
        if [ "$SDK_SOURCE" = "BRANCH_BUILDTYPE" ]; then
          BRANCH_BUILDTYPE="${SOURCE_SDK_NAME:-}"
        fi
      else
        PLATFORM="unknown"
        SDK_NAME="SDK_NAME_REQUIRED"
        SDK_SOURCE="ssh_failed"
      fi
    else
      # 无 SSH 时仅做本地平台检测
      if [ -d "$dir/vendor/sprd" ] || [ -d "$dir/device/sprd" ]; then
        PLATFORM="unisoc"
      elif [ -d "$dir/vendor/mediatek" ]; then
        PLATFORM="mtk"
      elif [ -d "$dir/device/rockchip" ]; then
        PLATFORM="rk"
      else
        PLATFORM="unknown"
      fi
      SDK_NAME="SDK_NAME_REQUIRED"
      SDK_SOURCE="no_ssh"
    fi

    echo "PROJECT_NAME=$SDK_NAME"
    echo "PROJECT_PATH=$dir"
    echo "PROJECT_NAME_SOURCE=$SDK_SOURCE"
    echo "PLATFORM=$PLATFORM"
    echo "REMOTE_ROOT=$remote_root"
    [ -n "${PROJECT_BRANCH:-}" ] && echo "PROJECT_BRANCH=$PROJECT_BRANCH"
    [ -n "${BRANCH_BUILDTYPE:-}" ] && echo "BRANCH_BUILDTYPE=$BRANCH_BUILDTYPE"
    echo ""
    found=1
  fi
done < <(list_local_directories)

if [ "$found" -eq 0 ]; then
  die 1 "未在 $mount_point 下检测到 Android 项目（需 .repo/ 或 build/+frameworks/）"
fi
