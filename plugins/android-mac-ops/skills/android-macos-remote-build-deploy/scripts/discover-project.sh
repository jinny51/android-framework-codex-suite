#!/usr/bin/env bash
set -euo pipefail
# 通过 SSH 发现远端 Android 构建配置：lunch target、product out、构建类型。

usage() {
  cat <<'USAGE'
用法:
  discover-project.sh --ssh-host HOST --remote-root PATH

选项:
  --ssh-host HOST       SSH 主机。必需。
  --remote-root PATH    远端 Android 源码根路径。必需。
  -h, --help            显示此帮助。

输出:
  LUNCH_TARGET, PRODUCT_OUT, BUILD_VARIANT, BUILD_CONFIG_SOURCE

退出码:
  0  成功
  2  缺少参数
  3  远端路径不存在
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

ssh_host=; remote_root=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host)    ssh_host="${2:?缺少 --ssh-host 的值}"; shift 2 ;;
    --remote-root) remote_root="${2:?缺少 --remote-root 的值}"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$ssh_host" ]   || die 2 "--ssh-host 是必需的"
[ -n "$remote_root" ] || die 2 "--remote-root 是必需的"

ssh -o ConnectTimeout=8 "$ssh_host" "bash -s -- $(printf '%q' "$remote_root")" <<'REMOTE'
set -euo pipefail
root="$1"
cd "$root" 2>/dev/null || { echo "REMOTE_ROOT_MISSING" >&2; exit 3; }

if [ -f .codex/build-push.config.sh ]; then
  lunch=$(grep -m1 '^LUNCH_TARGET=' .codex/build-push.config.sh 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
  [ -n "$lunch" ] && echo "LUNCH_TARGET=$lunch"
  echo "BUILD_CONFIG_SOURCE=.codex/build-push.config.sh"
fi

if [ -d out/target/product ]; then
  product=$(ls out/target/product/ 2>/dev/null | head -1 || true)
  [ -n "$product" ] && [ -d "out/target/product/$product" ] && echo "PRODUCT_OUT=out/target/product/$product"
fi

[ -n "${TARGET_BUILD_VARIANT:-}" ] && echo "BUILD_VARIANT=$TARGET_BUILD_VARIANT"

echo "DISCOVER_STATUS=ok"
REMOTE
