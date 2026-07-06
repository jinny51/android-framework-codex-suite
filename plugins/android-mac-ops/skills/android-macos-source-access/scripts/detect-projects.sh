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

  ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 "$ssh_host" bash -s <<REMOTE
set -euo pipefail
root="$remote_root"
[ -d "\$root" ] || { printf "REMOTE_ROOT_MISSING\n" >&2; exit 3; }

score_rk=0 score_unisoc=0 score_mtk=0

has_dir() { local p; for p in "\$@"; do [ -d "\$root/\$p" ] && return 0; done; return 1; }

first_assignment() {
  local pattern="\$1"; shift; local base file value
  for base in "\$@"; do
    [ -d "\$base" ] || continue
    while IFS= read -r -d "" file; do
      value="\$(grep -hsE "\$pattern" "\$file" 2>/dev/null | head -n1 | sed -E 's/.*:?=[[:space:]]*//; s/[[:space:]]+.*//' || true)"
      [ -n "\$value" ] && { printf "%s" "\$value"; return 0; }
    done < <(find "\$base" -maxdepth 4 -type f \( -name "*.mk" -o -name "*.bp" \) -print0 2>/dev/null)
  done
  return 0
}

# 平台打分
has_dir device/rockchip vendor/rockchip hardware/rockchip && score_rk=\$((score_rk+20))
has_dir device/sprd vendor/sprd vendor/unisoc hardware/sprd hardware/unisoc && score_unisoc=\$((score_unisoc+20))
has_dir device/mediatek vendor/mediatek hardware/mediatek && score_mtk=\$((score_mtk+20))

pv_rk="\$(first_assignment '^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=' "\$root/device/rockchip" "\$root/vendor/rockchip")"
pv_un="\$(first_assignment '^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=' "\$root/device/sprd" "\$root/vendor/sprd" "\$root/vendor/unisoc")"
pv_mt="\$(first_assignment '^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=' "\$root/device/mediatek" "\$root/vendor/mediatek")"

case "\$pv_rk" in rk*|RK*) score_rk=\$((score_rk+20)) ;; esac
case "\$pv_un" in ums*|uis*|udx*|sc*|sp*|shark*|qogir*|pike*) score_unisoc=\$((score_unisoc+20)) ;; esac
case "\$pv_mt" in mt[0-9]*|MT[0-9]*) score_mtk=\$((score_mtk+20)) ;; esac

source_platform=""; score=0
if [ "\$score_unisoc" -ge "\$score_rk" ] && [ "\$score_unisoc" -ge "\$score_mtk" ] && [ "\$score_unisoc" -gt 0 ]; then
  source_platform=unisoc; score=\$score_unisoc; platform_value="\$pv_un"
elif [ "\$score_mtk" -ge "\$score_rk" ] && [ "\$score_mtk" -ge "\$score_unisoc" ] && [ "\$score_mtk" -gt 0 ]; then
  source_platform=mtk; score=\$score_mtk; platform_value="\$pv_mt"
elif [ "\$score_rk" -gt 0 ]; then
  source_platform=rk; score=\$score_rk; platform_value="\$pv_rk"
fi

# SDK 名：先查 git branch
branch_for_repo() { [ -d "\$1/.git" ] || return 0; git -C "\$1" branch --show-current 2>/dev/null || true; }
useful_branch() {
  [ -n "\$1" ] || return 1
  case "\$1" in HEAD|master|main|develop|development|dev|release|stable) return 1;; android-*|refs/tags/*) return 1;; esac
  return 0
}

platform="\${source_platform:-unknown}"
case "\$platform" in
  rk)    product_roots=("\$root/device/rockchip" "\$root/vendor/rockchip") ;;
  unisoc) product_roots=("\$root/device/sprd" "\$root/vendor/sprd" "\$root/vendor/unisoc") ;;
  mtk)   product_roots=("\$root/device/mediatek" "\$root/vendor/mediatek") ;;
  *)     product_roots=() ;;
esac

project_branch=""
branch_dirs=("\$root/frameworks/base")
case "\$platform" in
  rk) [ -n "\$platform_value" ] && branch_dirs+=("\$root/device/rockchip/\$platform_value")
      branch_dirs+=("\$root/vendor/rockchip/common" "\$root/kernel" "\$root/u-boot") ;;
  unisoc) branch_dirs+=("\$root/device/sprd" "\$root/vendor/sprd" "\$root/vendor/unisoc" "\$root/kernel" "\$root/u-boot") ;;
  mtk) branch_dirs+=("\$root/device/mediatek" "\$root/vendor/mediatek" "\$root/kernel" "\$root/u-boot") ;;
esac

for dir in "\${branch_dirs[@]}"; do
  branch="\$(branch_for_repo "\$dir")"
  if useful_branch "\$branch"; then project_branch="\$branch"; break; fi
done

# SDK 名回退：BRANCH_BUILDTYPE
branch_buildtype=""
[ \${#product_roots[@]} -gt 0 ] && branch_buildtype="\$(first_assignment '^[[:space:]]*BRANCH_BUILDTYPE[[:space:]]*:?=' "\${product_roots[@]}")"

sdk_name=""; sdk_source=""
if [ -n "\$project_branch" ]; then
  sdk_name="\${project_branch##*/}"; sdk_source=project_branch
elif [ -n "\$branch_buildtype" ]; then
  sdk_name="\$branch_buildtype"; sdk_source=BRANCH_BUILDTYPE
else
  sdk_name="SDK_NAME_REQUIRED"; sdk_source=none
fi

printf "PLATFORM=%q\n" "\$platform"
printf "SDK_NAME=%q\n" "\$sdk_name"
printf "SDK_SOURCE=%q\n" "\$sdk_source"
printf "PROJECT_BRANCH=%q\n" "\${project_branch:-}"
printf "BRANCH_BUILDTYPE=%q\n" "\${branch_buildtype:-}"
printf "PLATFORM_SCORE_RK=%s\n" "\$score_rk"
printf "PLATFORM_SCORE_UNISOC=%s\n" "\$score_unisoc"
printf "PLATFORM_SCORE_MTK=%s\n" "\$score_mtk"
REMOTE
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
done < <(find "$mount_point" -maxdepth "$max_depth" -mindepth 1 -type d -print0 2>/dev/null)

if [ "$found" -eq 0 ]; then
  die 1 "未在 $mount_point 下检测到 Android 项目（需 .repo/ 或 build/+frameworks/）"
fi
