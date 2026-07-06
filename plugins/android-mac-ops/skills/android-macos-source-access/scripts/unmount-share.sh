#!/usr/bin/env bash
set -euo pipefail
# 卸载 macOS 上的 Samba 共享。

usage() {
  cat <<'USAGE'
用法:
  unmount-share.sh --mount-point /挂载/路径

选项:
  --mount-point PATH    要卸载的本地挂载点。必需。
  -h, --help            显示此帮助。

输出:
  UNMOUNT_STATUS         unmounted | not_mounted | failed
  MOUNT_POINT           挂载点路径。

退出码:
  0  成功或本来就没挂载
  2  缺少参数
  4  卸载失败
USAGE
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

mount_point=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mount-point) mount_point="${2:?缺少 --mount-point 的值}"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$mount_point" ] || die 2 "--mount-point 是必需的"

# ── 检查是否挂载 ──
if ! mount | grep -q " on $mount_point (" 2>/dev/null; then
  echo "UNMOUNT_STATUS=not_mounted"
  echo "MOUNT_POINT=$mount_point"
  exit 0
fi

# ── 卸载 ──
if ! umount "$mount_point" 2>/tmp/unmount-share.err; then
  err="$(cat /tmp/unmount-share.err 2>/dev/null || true)"
  rm -f /tmp/unmount-share.err
  die 4 "卸载失败: $err"
fi

echo "UNMOUNT_STATUS=unmounted"
echo "MOUNT_POINT=$mount_point"
