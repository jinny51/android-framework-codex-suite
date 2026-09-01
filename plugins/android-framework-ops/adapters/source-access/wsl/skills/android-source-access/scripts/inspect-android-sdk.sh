#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  inspect-android-sdk.sh --ssh-host HOST --remote-root /remote/sdk/root [options]

Inspect Android source exclusively through android-remote-channel v2. This
adapter never reads a CIFS mount and never invokes SSH directly.

Required integration:
  --channel-script PATH     android-remote-channel.sh from android-framework-ops.
  --inspection-helper PATH  remote_source_inspection.py from android-framework-ops.

The paths may instead be supplied with ANDROID_REMOTE_CHANNEL_SCRIPT and
ANDROID_REMOTE_SOURCE_INSPECTION_HELPER.

Options:
  --platform NAME             User-stated platform: unisoc, mtk, or rk.
  --sdk-name NAME             User-stated SDK/project name.
  --accept-platform-conflict  Continue after explicit user confirmation.
  --accept-sdk-name-conflict  Continue after explicit user confirmation.
  --mode strict|discovery     Default: strict.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

ssh_host=""
remote_root=""
platform=""
sdk_name=""
accept_platform_conflict=0
accept_sdk_name_conflict=0
mode=strict
channel_script="${ANDROID_REMOTE_CHANNEL_SCRIPT:-}"
inspection_helper="${ANDROID_REMOTE_SOURCE_INSPECTION_HELPER:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host) ssh_host="${2:?missing value for --ssh-host}"; shift 2 ;;
    --remote-root) remote_root="${2:?missing value for --remote-root}"; shift 2 ;;
    --platform) platform="${2:?missing value for --platform}"; shift 2 ;;
    --sdk-name) sdk_name="${2:?missing value for --sdk-name}"; shift 2 ;;
    --accept-platform-conflict) accept_platform_conflict=1; shift ;;
    --accept-sdk-name-conflict) accept_sdk_name_conflict=1; shift ;;
    --mode) mode="${2:?missing value for --mode}"; shift 2 ;;
    --channel-script) channel_script="${2:?missing value for --channel-script}"; shift 2 ;;
    --inspection-helper) inspection_helper="${2:?missing value for --inspection-helper}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$ssh_host" ] || die "--ssh-host is required"
[ -n "$remote_root" ] || die "--remote-root is required"
case "$platform" in ""|unisoc|mtk|rk) ;; *) die "unsupported platform '$platform'" ;; esac
case "$mode" in strict|discovery) ;; *) die "--mode must be strict or discovery" ;; esac
[ "$accept_platform_conflict" -eq 0 ] || [ -n "$platform" ] || die "--accept-platform-conflict requires --platform"
[ "$accept_sdk_name_conflict" -eq 0 ] || [ -n "$sdk_name" ] || die "--accept-sdk-name-conflict requires --sdk-name"
[ -f "$channel_script" ] || die "REMOTE_CHANNEL_REQUIRED: pass --channel-script or set ANDROID_REMOTE_CHANNEL_SCRIPT"
[ -f "$inspection_helper" ] || die "REMOTE_INSPECTION_HELPER_REQUIRED: pass --inspection-helper or set ANDROID_REMOTE_SOURCE_INSPECTION_HELPER"

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

exec python3 "$inspection_helper" "${args[@]}"
