#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  detect-projects.sh --ssh-host HOST --remote-root PATH [options]

Compatibility-named adapter for remote-only Android project inspection. It
never walks or reads the mounted SMB tree and never invokes SSH directly.

Required integration:
  --channel-script PATH     android-remote-channel.sh from android-framework-ops.
  --inspection-helper PATH  remote_source_inspection.py from android-framework-ops.

Options:
  --mount-point PATH          Record the human/artifact bridge path without inspecting it.
  --platform rk|mtk|unisoc    Explicit platform hint.
  --sdk-name NAME             Explicit project/SDK hint.
  --accept-platform-conflict  Continue after explicit user confirmation.
  --accept-sdk-name-conflict  Continue after explicit user confirmation.
  --mode strict|discovery     Default: strict.

The integration paths may instead be supplied with
ANDROID_REMOTE_CHANNEL_SCRIPT and ANDROID_REMOTE_SOURCE_INSPECTION_HELPER.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

ssh_host=""
remote_root=""
mount_point=""
platform=""
sdk_name=""
accept_platform_conflict=0
accept_sdk_name_conflict=0
mode=strict
channel_script="${ANDROID_REMOTE_CHANNEL_SCRIPT:-}"
inspection_helper="${ANDROID_REMOTE_SOURCE_INSPECTION_HELPER:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host) ssh_host="${2:?missing --ssh-host value}"; shift 2 ;;
    --remote-root) remote_root="${2:?missing --remote-root value}"; shift 2 ;;
    --mount-point) mount_point="${2:?missing --mount-point value}"; shift 2 ;;
    --platform) platform="${2:?missing --platform value}"; shift 2 ;;
    --sdk-name) sdk_name="${2:?missing --sdk-name value}"; shift 2 ;;
    --accept-platform-conflict) accept_platform_conflict=1; shift ;;
    --accept-sdk-name-conflict) accept_sdk_name_conflict=1; shift ;;
    --mode) mode="${2:?missing --mode value}"; shift 2 ;;
    --channel-script) channel_script="${2:?missing --channel-script value}"; shift 2 ;;
    --inspection-helper) inspection_helper="${2:?missing --inspection-helper value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$ssh_host" ] || die "--ssh-host is required"
[ -n "$remote_root" ] || die "--remote-root is required"
case "$platform" in ""|rk|mtk|unisoc) ;; *) die "unsupported platform '$platform'" ;; esac
case "$mode" in strict|discovery) ;; *) die "--mode must be strict or discovery" ;; esac
[ "$accept_platform_conflict" -eq 0 ] || [ -n "$platform" ] || die "--accept-platform-conflict requires --platform"
[ "$accept_sdk_name_conflict" -eq 0 ] || [ -n "$sdk_name" ] || die "--accept-sdk-name-conflict requires --sdk-name"
[ -f "$channel_script" ] || die "REMOTE_CHANNEL_REQUIRED: pass --channel-script or set ANDROID_REMOTE_CHANNEL_SCRIPT"
[ -f "$inspection_helper" ] || die "REMOTE_INSPECTION_HELPER_REQUIRED: pass --inspection-helper or set ANDROID_REMOTE_SOURCE_INSPECTION_HELPER"

inspection_env="$(mktemp "${TMPDIR:-/tmp}/android-mac-inspection.XXXXXX")"
trap 'rm -f "$inspection_env"' EXIT

args=(
  --channel-script "$channel_script"
  --ssh-host "$ssh_host"
  --remote-root "$remote_root"
  --mode "$mode"
)
[ -z "$platform" ] || args+=(--platform "$platform")
[ -z "$sdk_name" ] || args+=(--sdk-name "$sdk_name")
[ "$accept_platform_conflict" -eq 0 ] || args+=(--accept-platform-conflict)
[ "$accept_sdk_name_conflict" -eq 0 ] || args+=(--accept-sdk-name-conflict)

python3 "$inspection_helper" "${args[@]}" >"$inspection_env"
# shellcheck disable=SC1090
source "$inspection_env"

cat "$inspection_env"
printf 'PROJECT_NAME=%q\n' "$SDK_NAME"
printf 'PROJECT_NAME_SOURCE=%q\n' "${SOURCE_SDK_SOURCE:-none}"
printf 'MOUNT_TRANSPORT=%q\n' "smbfs"
if [ -n "$mount_point" ]; then
  printf 'ARTIFACT_BRIDGE_PATH=%q\n' "$mount_point"
fi
