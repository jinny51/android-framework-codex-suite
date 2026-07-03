#!/usr/bin/env bash
set -euo pipefail
# 生成或更新项目 .codex/build-push.config.sh。

usage() {
  cat <<'USAGE'
用法:
  generate-build-push.sh --repo PATH [选项]

选项:
  --repo PATH           本地项目路径。必需。
  --ssh-host HOST       远端 SSH 主机。
  --remote-root PATH    远端源码路径。
  --force               强制覆盖已有配置。
  -h, --help            显示此帮助。

退出码:
  0  成功
  2  缺少参数
  3  本地路径不存在
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

repo=; ssh_host=; remote_root=; force=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)        repo="${2:?缺少 --repo 的值}"; shift 2 ;;
    --ssh-host)    ssh_host="${2:?缺少 --ssh-host 的值}"; shift 2 ;;
    --remote-root) remote_root="${2:?缺少 --remote-root 的值}"; shift 2 ;;
    --force)       force=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$repo" ] || die 2 "--repo 是必需的"
[ -d "$repo" ] || die 3 "本地项目路径不存在: $repo"

codex_dir="$repo/.codex"
mkdir -p "$codex_dir"
config_file="$codex_dir/build-push.config.sh"

if [ -f "$config_file" ] && [ "$force" = false ]; then
  echo "CONFIG_STATUS=already_exists"
  echo "CONFIG_FILE=$config_file"
  exit 0
fi

cat > "$config_file" <<CFG
#!/usr/bin/env bash
# 自动生成的构建配置 — android-macos-remote-build-deploy
SSH_HOST="${ssh_host:-}"
REMOTE_ROOT="${remote_root:-}"
ENVSETUP_SCRIPT="build/envsetup.sh"
LUNCH_TARGET="\${LUNCH_TARGET:-}"
PRODUCT_OUT_DIR_REL="out/target/product/\$(echo \$LUNCH_TARGET | sed 's/_.*//')"
BUILD_PUSH_LOG_REL=".codex/build-push.log"
CFG

chmod +x "$config_file"
echo "CONFIG_STATUS=generated"
echo "CONFIG_FILE=$config_file"
