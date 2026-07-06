param(
    [Parameter(Mandatory = $true)]
    [string]$SshHost,

    [Parameter(Mandatory = $true)]
    [string]$RemoteRoot,

    [ValidateSet("", "rk", "unisoc", "mtk")]
    [string]$Platform = "",

    [string]$SdkName = "",

    [switch]$AcceptPlatformConflict,
    [switch]$AcceptSdkNameConflict
)

$ErrorActionPreference = "Stop"

function Quote-BashArg([string]$Value) {
    if ($null -eq $Value) { $Value = "" }
    return "'" + $Value.Replace("'", "'\''") + "'"
}

$remoteScript = @'
set -euo pipefail

root="$1"
platform_override="${2:-}"
sdk_name_override="${3:-}"
accept_platform_conflict="${4:-0}"
accept_sdk_name_conflict="${5:-0}"

[ -d "$root" ] || { echo "REMOTE_ROOT_MISSING path=$root" >&2; exit 3; }
[ -d "$root/frameworks/base" ] || [ -d "$root/build" ] || [ -d "$root/.repo" ] || {
  echo "ANDROID_MARKERS_MISSING path=$root" >&2
  exit 4
}

score_rk=0
score_unisoc=0
score_mtk=0

has_dir() {
  for p in "$@"; do
    [ -d "$root/$p" ] && return 0
  done
  return 1
}

has_dir device/rockchip vendor/rockchip hardware/rockchip && score_rk=$((score_rk + 20))
has_dir device/sprd vendor/sprd vendor/unisoc hardware/sprd hardware/unisoc && score_unisoc=$((score_unisoc + 20))
has_dir device/mediatek vendor/mediatek hardware/mediatek device/mtk vendor/mtk hardware/mtk && score_mtk=$((score_mtk + 20))

platform_value="$(
  find "$root/device" "$root/vendor" -maxdepth 5 -type f \( -name "*.mk" -o -name "BoardConfig.mk" \) 2>/dev/null \
    -exec grep -hsE "^[[:space:]]*TARGET_BOARD_PLATFORM[[:space:]]*:?=" {} + \
    | head -n 1 \
    | sed -E "s/.*:?=[[:space:]]*//; s/[[:space:]]+.*//" || true
)"

case "$platform_value" in
  rk*|RK*) score_rk=$((score_rk + 20)) ;;
  ums*|uis*|udx*|sc*|sp*|shark*|qogir*|pike*) score_unisoc=$((score_unisoc + 20)) ;;
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

if [ -n "$source_platform" ] && [ "$score" -ge 10 ] && [ -n "$platform_override" ] && [ "$platform_override" != "$source_platform" ]; then
  if [ "$accept_platform_conflict" != "1" ]; then
    echo "PLATFORM_CONFLICT user_platform=$platform_override source_platform=$source_platform scores=rk:$score_rk,unisoc:$score_unisoc,mtk:$score_mtk target_board_platform=$platform_value" >&2
    exit 7
  fi
fi

platform="$source_platform"
if [ -n "$platform_override" ]; then
  platform="$platform_override"
elif [ -z "$platform" ] || [ "$score" -lt 10 ]; then
  echo "PLATFORM_REQUIRED reason=source_inspection_unknown scores=rk:$score_rk,unisoc:$score_unisoc,mtk:$score_mtk target_board_platform=$platform_value" >&2
  exit 5
fi

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
for dir in \
  "$root/frameworks/base" \
  "$root/device/sprd" \
  "$root/vendor/sprd" \
  "$root/vendor/unisoc" \
  "$root/device/rockchip" \
  "$root/vendor/rockchip" \
  "$root/device/mediatek" \
  "$root/vendor/mediatek" \
  "$root/device/mtk" \
  "$root/vendor/mtk" \
  "$root/kernel" \
  "$root/u-boot"
do
  branch="$(branch_for_repo "$dir")"
  if useful_branch "$branch"; then
    project_branch="$branch"
    break
  fi
done

branch_buildtype=""
case "$platform" in
  rk) product_roots=("$root/device/rockchip" "$root/vendor/rockchip") ;;
  unisoc) product_roots=("$root/device/sprd" "$root/vendor/sprd" "$root/vendor/unisoc" "$root/device/unisoc") ;;
  mtk) product_roots=("$root/device/mediatek" "$root/vendor/mediatek" "$root/device/mtk" "$root/vendor/mtk") ;;
esac

for product_root in "${product_roots[@]}"; do
  [ -d "$product_root" ] || continue
  branch_buildtype="$(
    find "$product_root" -maxdepth 5 -type f -name "*.mk" 2>/dev/null \
      -exec grep -hsE "^[[:space:]]*BRANCH_BUILDTYPE[[:space:]]*:?=" {} + \
      | head -n 1 \
      | sed -E "s/.*:?=[[:space:]]*//; s/[[:space:]]+.*//" || true
  )"
  [ -n "$branch_buildtype" ] && break
done

android_product_name=""
for product_root in "${product_roots[@]}"; do
  [ -d "$product_root" ] || continue
  android_product_name="$(
    find "$product_root" -maxdepth 5 -type f -name "*.mk" 2>/dev/null \
      -exec grep -hsE "^[[:space:]]*PRODUCT_NAME[[:space:]]*:?=" {} + \
      | head -n 1 \
      | sed -E "s/.*:?=[[:space:]]*//; s/[[:space:]]+.*//" || true
  )"
  [ -n "$android_product_name" ] && break
done

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
  if [ -n "$source_sdk_name" ] && [ "$sdk_name_override" != "$source_sdk_name" ] && [ "$accept_sdk_name_conflict" != "1" ]; then
    echo "SDK_NAME_CONFLICT user_sdk=$sdk_name_override source_sdk=$source_sdk_name source=$source_sdk_source project_branch=$project_branch branch_buildtype=$branch_buildtype" >&2
    exit 8
  fi
  sdk_name="$sdk_name_override"
elif [ -n "$source_sdk_name" ]; then
  sdk_name="$source_sdk_name"
else
  echo "SDK_NAME_REQUIRED reason=no_project_branch_or_branch_buildtype platform=$platform root=$root" >&2
  exit 6
fi

printf "PLATFORM=%s\n" "$platform"
printf "SDK_NAME=%s\n" "$sdk_name"
printf "SOURCE_PLATFORM=%s\n" "$source_platform"
printf "SOURCE_SDK_NAME=%s\n" "$source_sdk_name"
printf "SOURCE_SDK_SOURCE=%s\n" "$source_sdk_source"
printf "PROJECT_BRANCH=%s\n" "$project_branch"
printf "ANDROID_PRODUCT_NAME=%s\n" "$android_product_name"
printf "TARGET_BOARD_PLATFORM=%s\n" "$platform_value"
printf "PLATFORM_SCORE_RK=%s\n" "$score_rk"
printf "PLATFORM_SCORE_UNISOC=%s\n" "$score_unisoc"
printf "PLATFORM_SCORE_MTK=%s\n" "$score_mtk"
'@

$args = @(
    (Quote-BashArg $RemoteRoot),
    (Quote-BashArg $Platform),
    (Quote-BashArg $SdkName),
    (Quote-BashArg ($(if ($AcceptPlatformConflict) { "1" } else { "0" }))),
    (Quote-BashArg ($(if ($AcceptSdkNameConflict) { "1" } else { "0" })))
) -join " "

$sshCommand = "bash -s -- $args"
$output = $remoteScript | & ssh.exe -o BatchMode=yes -o ConnectTimeout=8 $SshHost $sshCommand 2>&1
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw (($output | Out-String).Trim())
}

$result = [ordered]@{}
foreach ($line in $output) {
    if ($line -match "^([^=]+)=(.*)$") {
        $result[$matches[1]] = $matches[2]
    }
}

$result | ConvertTo-Json -Depth 4
