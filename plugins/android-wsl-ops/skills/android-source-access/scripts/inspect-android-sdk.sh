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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
remote_inspector="$script_dir/../../../lib/android_source_access/remote_inspector.sh"
[ -r "$remote_inspector" ] || {
  echo "remote SDK inspector is missing: $remote_inspector" >&2
  exit 3
}

remote_command="bash -s -- $(printf '%q' "$remote_root") $(printf '%q' "$platform_override") $(printf '%q' "$sdk_name_override") $(printf '%q' "$accept_platform_conflict") $(printf '%q' "$accept_sdk_name_conflict") strict"
connect_timeout="${SSH_CONNECT_TIMEOUT:-10}"
ssh \
  -o BatchMode=yes \
  -o ConnectTimeout="$connect_timeout" \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 \
  "$ssh_host" \
  "$remote_command" \
  <"$remote_inspector"
