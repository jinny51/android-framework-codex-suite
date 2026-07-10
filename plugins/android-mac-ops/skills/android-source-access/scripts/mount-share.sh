#!/usr/bin/env bash
set -euo pipefail
# 在 macOS 上通过原生 mount -t smbfs 挂载 Samba 共享。
# 无需 sudo，macOS 允许用户态 SMB 挂载。
#
# 支持 Keychain 凭据读取:
#   --keychain 从 macOS Keychain 读取 SMB 密码
#   --save-credentials 挂载成功后保存密码到 Keychain

usage() {
  cat <<'USAGE_EOF'
用法:
  mount-share.sh --share //server/share --mount-point /本地/路径 [选项]

选项:
  --share URL            Samba 地址，如 //192.168.100.23/unisoc。必需。
  --mount-point PATH     本地挂载目录。不存在则自动创建。必需；应位于 $HOME/work 下。
  --user USER            Samba 用户名。除非 --guest，否则必需。
  --password-env NAME    Samba 密码所在环境变量名。默认: SAMBA_PASSWORD。
  --guest                无凭据挂载（匿名/游客）。
  --keychain             从 macOS Keychain 读取 SMB 密码（需同时 --remote-user --server）。
  --remote-user USER     Keychain 查询用的远端用户名。
  --server HOST          Keychain 查询用的服务器 IP/主机名。
  --save-credentials     挂载成功后保存密码到 Keychain。
  --non-interactive      缺少密码时直接失败，不进入交互提示。
  -h, --help             显示此帮助。

密码优先级:
  1. --password-env 指定的环境变量
  2. --keychain 从 Keychain 读取
  3. 提示用户输入

输出 (KEY=VALUE):
  MOUNT_POINT            本地挂载点。
  MOUNT_STATUS           mounted | already_mounted。
  SHARE_URL              挂载的 Samba 地址。

退出码:
  0  成功或已挂载
  2  缺少参数／参数格式错误
  3  挂载点非空（拒绝覆盖已有文件）
  4  mount 命令执行失败
  5  缺少密码
  6  挂载成功但 Keychain 保存失败
USAGE_EOF
}

die() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "$code"
}

share=
mount_point=
user=
password_env=SAMBA_PASSWORD
guest=0
use_keychain=0
remote_user=
server=
save_creds=0
non_interactive=0
script_dir="$(cd "$(dirname "$0")" && pwd)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --share)             share="${2:?缺少 --share 的值}"; shift 2 ;;
    --mount-point)       mount_point="${2:?缺少 --mount-point 的值}"; shift 2 ;;
    --user)              user="${2:?缺少 --user 的值}"; shift 2 ;;
    --password-env)      password_env="${2:?缺少 --password-env 的值}"; shift 2 ;;
    --guest)             guest=1; shift ;;
    --keychain)          use_keychain=1; shift ;;
    --remote-user)       remote_user="${2:?缺少 --remote-user 的值}"; shift 2 ;;
    --server)            server="${2:?缺少 --server 的值}"; shift 2 ;;
    --save-credentials)  save_creds=1; shift ;;
    --non-interactive)   non_interactive=1; shift ;;
    -h|--help)           usage; exit 0 ;;
    *)                   die 2 "未知参数: $1" ;;
  esac
done

# 参数校验
[ -n "$share" ]       || die 2 "--share 是必需的"
[ -n "$mount_point" ] || die 2 "--mount-point 是必需的"

case "$share" in
  //*/*) ;;
  *) die 2 "--share 格式必须为 //server/share，当前值: $share" ;;
esac

if [ "$use_keychain" -eq 1 ] || [ "$save_creds" -eq 1 ]; then
  [ -n "$remote_user" ] || die 2 "--keychain/--save-credentials 需要 --remote-user"
  [ -n "$server" ] || die 2 "--keychain/--save-credentials 需要 --server"
fi

akbs_root="${AKBS_ROOT:-$HOME/akbs}"
work_root="${ANDROID_WORK_ROOT:-$HOME/work}"
case "$mount_point" in
  "$akbs_root"|"$akbs_root"/*)
    die 2 "Android 源码不能挂到 AKBS_ROOT 下: ${mount_point}；请使用 Android work root: ${work_root}"
    ;;
esac
case "$mount_point" in
  "$work_root"|"$work_root"/*) ;;
  *) die 2 "Android 源码挂载点必须位于 Android work root 下: ${work_root}" ;;
esac

# 检查是否已挂载
if mount | grep -q " on $mount_point (" 2>/dev/null; then
  echo "MOUNT_POINT=$mount_point"
  echo "MOUNT_STATUS=already_mounted"
  echo "SHARE_URL=$share"
  exit 0
fi

# 检查目标目录
if [ -d "$mount_point" ] && [ -n "$(ls -A "$mount_point" 2>/dev/null)" ]; then
  die 3 "挂载点非空: ${mount_point}（拒绝覆盖已有文件，请先清空或卸载）"
fi

mkdir -p "$mount_point" || die 4 "无法创建挂载目录: $mount_point"

# 获取密码（优先级: env var > Keychain > 提示）
password=""
mount_url=""

if [ "$guest" -ne 1 ]; then
  [ -n "$user" ] || die 2 "非 guest 模式需要 --user"

  # 优先级 1: 环境变量
  password="${!password_env-}"

  # 优先级 2: Keychain
  if [ -z "$password" ] && [ "$use_keychain" -eq 1 ]; then
    # shellcheck disable=SC1091
    source "$script_dir/_keychain_helpers.sh"
    password="$(credential_read "smb" "$remote_user" "$server")"
  fi

  # 优先级 3: 提示用户
  if [ -z "$password" ]; then
    [ "$non_interactive" -eq 0 ] || die 5 "Keychain 中没有 ${remote_user}@${server} 的 SMB/Samba 密码"
    echo "SMB_PASSWORD_REQUIRED: 请输入 $user@$server 的 SMB 密码" >&2
    read -r -s -p "SMB 密码: " password
    echo >&2
  fi

  [ -n "$password" ] || die 5 "无法获取 SMB 密码"

  share_body="${share#//}"
  mount_url="//${user}:${password}@${share_body}"
fi

# 挂载
mount_error_file="$(mktemp "${TMPDIR:-/tmp}/android-mac-mount.XXXXXX")"
trap 'rm -f "$mount_error_file"' EXIT
mount_ok=false
if [ "$guest" -eq 1 ]; then
  if mount -t smbfs "$share" "$mount_point" 2>"$mount_error_file"; then
    mount_ok=true
  fi
else
  if mount -t smbfs "$mount_url" "$mount_point" 2>"$mount_error_file"; then
    mount_ok=true
  fi
fi

if [ "$mount_ok" = false ]; then
  err="$(cat "$mount_error_file" 2>/dev/null || true)"
  # 如果密码来自 Keychain 但失败了，标记为可能过期
  if [ "$use_keychain" -eq 1 ] && [ -n "$remote_user" ] && [ -n "$server" ]; then
    # shellcheck disable=SC1091
    source "$script_dir/_keychain_helpers.sh" 2>/dev/null || true
    hash="$(account_key "$remote_user" "$server" 2>/dev/null || echo "")"
    if [ -n "$hash" ]; then
      env_file="$(keychain_env_path "$hash")"
      keychain_env_set "$env_file" "SMB_PASSWORD_STATE" "failed" 2>/dev/null || true
    fi
  fi
  die 4 "Samba 挂载失败: $err"
fi
rm -f "$mount_error_file"

# 挂载成功，保存凭据（如果 --save-credentials）
if [ "$save_creds" -eq 1 ] && [ "$guest" -ne 1 ] && [ -n "$remote_user" ] && [ -n "$server" ]; then
  # shellcheck disable=SC1091
  source "$script_dir/_keychain_helpers.sh"
  export CODEX_TARGET_PASSWORD="$password"
  if ! "$script_dir/keychain-store.sh" \
    --role smb \
    --remote-user "$remote_user" \
    --server "$server" >/dev/null; then
    unset CODEX_TARGET_PASSWORD
    password=""
    mount_url=""
    die 6 "挂载已成功，但 Keychain 保存失败"
  fi
  unset CODEX_TARGET_PASSWORD
fi

# 清理内存中的密码
password=""
mount_url=""

echo "MOUNT_POINT=$mount_point"
echo "MOUNT_STATUS=mounted"
echo "SHARE_URL=$share"
