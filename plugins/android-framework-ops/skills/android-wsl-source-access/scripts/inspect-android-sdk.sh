#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  inspect-android-sdk.sh --ssh-host HOST --remote-root /remote/sdk/root [options]

Inspect an Android SDK source root over SSH and quickly infer:
  PLATFORM: rk, unisoc, or mtk
  SDK_NAME: best local project folder name, preferring key-repo branch names
            such as frameworks/base or device/vendor/kernel branches
  PROJECT_BRANCH: branch used as the SDK/project name when found
  ANDROID_PRODUCT_NAME: Android lunch/product name when found
  TARGET_BOARD_PLATFORM: SoC/platform value when found

The remote path is treated only as a source root. Path segments such as
work/unisoc or the final directory basename are not used as platform/project
fallbacks. If source inspection cannot determine a missing platform or project
name, the script stops and asks the caller to collect that value from the user.
If user-stated values conflict with source evidence, the script reports a
conflict and stops instead of choosing a side unless the caller passes an
explicit accept flag after user confirmation.

Options:
  --platform NAME             User-stated platform. Must be unisoc, mtk, or rk.
  --sdk-name NAME             User-stated SDK/project name.
  --accept-platform-conflict  Continue when --platform conflicts with source evidence.
  --accept-sdk-name-conflict  Continue when --sdk-name conflicts with source evidence.
USAGE
}

ssh_host=
remote_root=
platform_override=
sdk_name_override=
accept_platform_conflict=0
accept_sdk_name_conflict=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host) ssh_host="${2:?missing value for --ssh-host}"; shift 2 ;;
    --remote-root) remote_root="${2:?missing value for --remote-root}"; shift 2 ;;
    --platform) platform_override="${2:?missing value for --platform}"; shift 2 ;;
    --sdk-name) sdk_name_override="${2:?missing value for --sdk-name}"; shift 2 ;;
    --accept-platform-conflict) accept_platform_conflict=1; shift ;;
    --accept-sdk-name-conflict) accept_sdk_name_conflict=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$ssh_host" ] || { echo "--ssh-host is required" >&2; exit 2; }
[ -n "$remote_root" ] || { echo "--remote-root is required" >&2; exit 2; }
if [ -n "$platform_override" ]; then
  case "$platform_override" in
    unisoc|mtk|rk) ;;
    *) echo "unsupported platform '$platform_override'; expected unisoc, mtk, or rk" >&2; exit 2 ;;
  esac
fi
if [ "$accept_platform_conflict" -eq 1 ] && [ -z "$platform_override" ]; then
  echo "--accept-platform-conflict requires --platform" >&2
  exit 2
fi
if [ "$accept_sdk_name_conflict" -eq 1 ] && [ -z "$sdk_name_override" ]; then
  echo "--accept-sdk-name-conflict requires --sdk-name" >&2
  exit 2
fi

remote_script='
set -euo pipefail
root="$1"
platform_override="$2"
sdk_name_override="$3"
accept_platform_conflict="$4"
accept_sdk_name_conflict="$5"
[ -d "$root" ] || { echo "REMOTE_ROOT_MISSING path=$root" >&2; exit 3; }
[ -d "$root/frameworks/base" ] || [ -d "$root/build" ] || [ -d "$root/.repo" ] || {
  echo "ANDROID_MARKERS_MISSING path=$root" >&2
  exit 4
}

score_rk=0
score_unisoc=0
score_mtk=0

has_dir() {
  local p
  for p in "$@"; do
    [ -d "$root/$p" ] && return 0
  done
  return 1
}

first_assignment() {
  local pattern="$1"
  shift
  local base file value
  for base in "$@"; do
    [ -d "$base" ] || continue
    while IFS= read -r -d "" file; do
      value="$(grep -hsE "$pattern" "$file" | head -n 1 | sed -E "s/.*:?=[[:space:]]*//; s/[[:space:]]+.*//" || true)"
      if [ -n "$value" ]; then
        printf "%s" "$value"
        return 0
      fi
    done < <(find "$base" -maxdepth 4 -type f \( -name "*.mk" -o -name "*.bp" -o -name "*.conf" -o -name "*.sh" \) -print0 2>/dev/null)
  done
  return 0
}

has_dir device/rockchip vendor/rockchip hardware/rockchip && score_rk=$((score_rk + 20))
has_dir device/sprd vendor/sprd vendor/unisoc hardware/sprd hardware/unisoc && score_unisoc=$((score_unisoc + 20))
has_dir device/mediatek vendor/mediatek hardware/mediatek device/mtk vendor/mtk hardware/mtk && score_mtk=$((score_mtk + 20))

platform_value_rk="$(first_assignment "^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=" "$root/device/rockchip" "$root/vendor/rockchip")"
platform_value_unisoc="$(first_assignment "^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=" "$root/device/sprd" "$root/vendor/sprd" "$root/vendor/unisoc" "$root/device/unisoc")"
platform_value_mtk="$(first_assignment "^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=" "$root/device/mediatek" "$root/vendor/mediatek" "$root/device/mtk" "$root/vendor/mtk")"

case "$platform_value_rk" in
  rk*|RK*) score_rk=$((score_rk + 20)) ;;
esac
case "$platform_value_unisoc" in
  ums*|uis*|udx*|sc*|sp*|shark*|qogir*|pike*) score_unisoc=$((score_unisoc + 20)) ;;
esac
case "$platform_value_mtk" in
  mt[0-9]*|MT[0-9]*) score_mtk=$((score_mtk + 20)) ;;
esac

if find "$root/device" "$root/vendor" "$root/hardware" -maxdepth 3 -type d -iname "*rockchip*" 2>/dev/null | head -n 1 | grep -q .; then
  score_rk=$((score_rk + 10))
fi
if find "$root/device" "$root/vendor" "$root/hardware" -maxdepth 3 -type d \( -iname "*sprd*" -o -iname "*unisoc*" \) 2>/dev/null | head -n 1 | grep -q .; then
  score_unisoc=$((score_unisoc + 10))
fi
if find "$root/device" "$root/vendor" "$root/hardware" -maxdepth 3 -type d \( -iname "*mediatek*" -o -iname "*mtk*" \) 2>/dev/null | head -n 1 | grep -q .; then
  score_mtk=$((score_mtk + 10))
fi

source_platform=""
score=0
if [ "$score_rk" -gt "$score" ]; then source_platform=rk; score="$score_rk"; fi
if [ "$score_unisoc" -gt "$score" ]; then source_platform=unisoc; score="$score_unisoc"; fi
if [ "$score_mtk" -gt "$score" ]; then source_platform=mtk; score="$score_mtk"; fi

platform_value=""
case "${platform_override:-$source_platform}" in
  rk) platform_value="$platform_value_rk" ;;
  unisoc) platform_value="$platform_value_unisoc" ;;
  mtk) platform_value="$platform_value_mtk" ;;
esac
if [ -z "$platform_value" ]; then
  platform_value="${platform_value_rk:-${platform_value_unisoc:-$platform_value_mtk}}"
fi

if [ -n "$source_platform" ] && [ "$score" -ge 10 ] && [ -n "$platform_override" ] && [ "$platform_override" != "$source_platform" ]; then
  if [ "$accept_platform_conflict" != "1" ]; then
    echo "PLATFORM_CONFLICT user_platform=$platform_override source_platform=$source_platform scores=rk:$score_rk,unisoc:$score_unisoc,mtk:$score_mtk target_board_platform=$platform_value" >&2
    exit 7
  fi
  echo "PLATFORM_CONFLICT_ACCEPTED user_platform=$platform_override source_platform=$source_platform scores=rk:$score_rk,unisoc:$score_unisoc,mtk:$score_mtk target_board_platform=$platform_value" >&2
fi

platform="$source_platform"
if [ -n "$platform_override" ]; then
  platform="$platform_override"
elif [ -z "$platform" ] || [ "$score" -lt 10 ]; then
  echo "PLATFORM_REQUIRED reason=source_inspection_unknown scores=rk:$score_rk,unisoc:$score_unisoc,mtk:$score_mtk target_board_platform=$platform_value" >&2
  exit 5
fi

sdk_name=""

case "$platform" in
  rk) product_roots=("$root/device/rockchip" "$root/vendor/rockchip") ;;
  unisoc) product_roots=("$root/device/sprd" "$root/vendor/sprd" "$root/vendor/unisoc" "$root/device/unisoc") ;;
  mtk) product_roots=("$root/device/mediatek" "$root/vendor/mediatek" "$root/device/mtk" "$root/vendor/mtk") ;;
esac

branch_for_repo() {
  local dir="$1"
  [ -d "$dir/.git" ] || return 0
  git -C "$dir" branch --show-current 2>/dev/null || true
}

useful_branch() {
  local branch="$1"
  [ -n "$branch" ] || return 1
  case "$branch" in
    HEAD|master|main|develop|development|dev|release|stable) return 1 ;;
    android-*|refs/tags/*) return 1 ;;
  esac
  return 0
}

project_branch=""
declare -a branch_dirs=("$root/frameworks/base")
case "$platform" in
  rk)
    [ -n "$platform_value" ] && branch_dirs+=("$root/device/rockchip/$platform_value")
    branch_dirs+=("$root/vendor/rockchip/common" "$root/kernel" "$root/u-boot")
    ;;
  unisoc)
    branch_dirs+=("$root/device/sprd" "$root/vendor/sprd" "$root/vendor/unisoc" "$root/kernel" "$root/u-boot")
    ;;
  mtk)
    branch_dirs+=("$root/device/mediatek" "$root/vendor/mediatek" "$root/device/mtk" "$root/vendor/mtk" "$root/kernel" "$root/u-boot")
    ;;
esac

for dir in "${branch_dirs[@]}"; do
  branch="$(branch_for_repo "$dir")"
  if useful_branch "$branch"; then
    project_branch="$branch"
    break
  fi
done

branch_buildtype="$(first_assignment "^[[:space:]]*BRANCH_BUILDTYPE[[:space:]]*:?=" "${product_roots[@]}")"
android_product_name=""

if [ "$platform" = "rk" ] && [ -n "$platform_value" ] && [ -f "$root/device/rockchip/$platform_value/AndroidProducts.mk" ]; then
  first_product_mk="$(grep -E "^[[:space:]]*(\\$\\(LOCAL_DIR\\)/)?[^[:space:]\\\\]+\\.mk" "$root/device/rockchip/$platform_value/AndroidProducts.mk" 2>/dev/null | head -n 1 | sed -E "s/[[:space:]\\\\]//g; s#\\$\\(LOCAL_DIR\\)#$root/device/rockchip/$platform_value#")"
  if [ -n "$first_product_mk" ] && [ -f "$first_product_mk" ]; then
    android_product_name="$(grep -hsE "^[[:space:]]*PRODUCT_NAME[[:space:]]*:?=" "$first_product_mk" 2>/dev/null | head -n 1 | sed -E "s/.*:?=[[:space:]]*//; s/[[:space:]]+.*//" || true)"
  fi
fi

if [ -z "$android_product_name" ]; then
  android_product_name="$(first_assignment "^[[:space:]]*PRODUCT_NAME[[:space:]]*:?=" "${product_roots[@]}")"
fi

source_sdk_name=""
source_sdk_source=""
if [ -n "$project_branch" ]; then
  source_sdk_name="${project_branch##*/}"
  source_sdk_source=project_branch
elif [ -n "$branch_buildtype" ]; then
  source_sdk_name="$branch_buildtype"
  source_sdk_source=BRANCH_BUILDTYPE
fi

if [ -n "$sdk_name_override" ]; then
  if [ -n "$source_sdk_name" ] && [ "$sdk_name_override" != "$source_sdk_name" ]; then
    if [ "$accept_sdk_name_conflict" != "1" ]; then
      echo "SDK_NAME_CONFLICT user_sdk=$sdk_name_override source_sdk=$source_sdk_name source=$source_sdk_source project_branch=$project_branch branch_buildtype=$branch_buildtype" >&2
      exit 8
    fi
    echo "SDK_NAME_CONFLICT_ACCEPTED user_sdk=$sdk_name_override source_sdk=$source_sdk_name source=$source_sdk_source project_branch=$project_branch branch_buildtype=$branch_buildtype" >&2
  fi
  sdk_name="$sdk_name_override"
elif [ -n "$source_sdk_name" ]; then
  sdk_name="$source_sdk_name"
else
  echo "SDK_NAME_REQUIRED reason=no_project_branch_or_branch_buildtype platform=$platform root=$root" >&2
  exit 6
fi

printf "PLATFORM=%q\n" "$platform"
printf "SDK_NAME=%q\n" "$sdk_name"
printf "SOURCE_PLATFORM=%q\n" "$source_platform"
printf "SOURCE_SDK_NAME=%q\n" "$source_sdk_name"
printf "SOURCE_SDK_SOURCE=%q\n" "$source_sdk_source"
printf "PROJECT_BRANCH=%q\n" "$project_branch"
printf "ANDROID_PRODUCT_NAME=%q\n" "$android_product_name"
printf "TARGET_BOARD_PLATFORM=%q\n" "$platform_value"
printf "PLATFORM_SCORE_RK=%q\n" "$score_rk"
printf "PLATFORM_SCORE_UNISOC=%q\n" "$score_unisoc"
printf "PLATFORM_SCORE_MTK=%q\n" "$score_mtk"
'

connect_timeout="${SSH_CONNECT_TIMEOUT:-10}"
ssh \
  -o BatchMode=yes \
  -o ConnectTimeout="$connect_timeout" \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 \
  "$ssh_host" \
  "bash -s -- $(printf '%q' "$remote_root") $(printf '%q' "$platform_override") $(printf '%q' "$sdk_name_override") $(printf '%q' "$accept_platform_conflict") $(printf '%q' "$accept_sdk_name_conflict")" \
  <<<"$remote_script"
