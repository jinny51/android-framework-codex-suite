#!/usr/bin/env bash
set -euo pipefail
# 确保远端 .codex/build-session.sh 存在，用于 android-remote-channel 持久构建会话。

usage() {
  cat <<'USAGE'
用法:
  ensure-build-session.sh --ssh-host HOST --remote-root PATH [--force]

选项:
  --ssh-host HOST       SSH 主机。必需。
  --remote-root PATH    远端源码根路径。必需。
  --force               强制重新生成（即使已存在）。
  -h, --help            显示此帮助。

退出码:
  0  成功（已存在或已创建）
  2  缺少参数
  3  SSH 连接失败
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

ssh_host=; remote_root=; force=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host)    ssh_host="${2:?缺少 --ssh-host 的值}"; shift 2 ;;
    --remote-root) remote_root="${2:?缺少 --remote-root 的值}"; shift 2 ;;
    --force)       force=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$ssh_host" ]   || die 2 "--ssh-host 是必需的"
[ -n "$remote_root" ] || die 2 "--remote-root 是必需的"

rq="$(printf '%q' "$remote_root")"

if [ "$force" = false ] && ssh -o ConnectTimeout=8 "$ssh_host" "test -f $rq/.codex/build-session.sh" 2>/dev/null; then
  echo "BUILD_SESSION_STATUS=already_exists"
  echo "BUILD_SESSION_PATH=$remote_root/.codex/build-session.sh"
  exit 0
fi

ssh "$ssh_host" "mkdir -p $rq/.codex && cat > $rq/.codex/build-session.sh && chmod +x $rq/.codex/build-session.sh" <<'SESSION'
#!/usr/bin/env bash
export ANDROID_BUILD_TOP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ANDROID_BUILD_TOP"
[ -f build/envsetup.sh ] && source build/envsetup.sh
[ -f .codex/build-push.config.sh ] && source .codex/build-push.config.sh
echo "[build-session] ready at $ANDROID_BUILD_TOP"
SESSION

echo "BUILD_SESSION_STATUS=created"
echo "BUILD_SESSION_PATH=$remote_root/.codex/build-session.sh"
