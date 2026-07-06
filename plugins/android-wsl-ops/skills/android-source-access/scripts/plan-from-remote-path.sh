#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  plan-from-remote-path.sh --remote-root /home/<user>/<sdk-root> [options]

Parse only the connection basics for an Android source mount plan. The remote
path is not used to infer platform or project name; source inspection or
explicit user input must provide those values.

Rules:
  /home/test61/mtk/tb8788p1 means only:
    REMOTE_USER=test61
    SSH_HOST=test61

Options:
  --remote-root PATH    Remote Android SDK root path. Required.
  --ssh-host HOST       Override SSH host/alias. Default: remote user.
  --local-platform NAME User-stated local platform folder.
  --sdk-name NAME       User-stated local SDK/project directory name.
  --mount-root PATH     Local mount root. Default: $ANDROID_WORK_ROOT or $HOME/work.
  -h, --help            Show this help.

Output:
  Shell-style KEY=VALUE lines.
USAGE
}

remote_root=
ssh_host=
local_platform_override=
sdk_name_override=
mount_root="${ANDROID_WORK_ROOT:-$HOME/work}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --remote-root) remote_root="${2:?missing value for --remote-root}"; shift 2 ;;
    --ssh-host) ssh_host="${2:?missing value for --ssh-host}"; shift 2 ;;
    --local-platform) local_platform_override="${2:?missing value for --local-platform}"; shift 2 ;;
    --sdk-name) sdk_name_override="${2:?missing value for --sdk-name}"; shift 2 ;;
    --mount-root) mount_root="${2:?missing value for --mount-root}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$remote_root" ] || { echo "--remote-root is required" >&2; exit 2; }
case "$remote_root" in
  //home/*) remote_root="/${remote_root#//}" ;;
esac

case "$remote_root" in
  /home/*/*) ;;
  *)
    echo "remote root must look like /home/<user>/<sdk-root>: $remote_root" >&2
    exit 2
    ;;
esac

trimmed="${remote_root#/home/}"
remote_user="${trimmed%%/*}"
platform="$local_platform_override"
sdk_name="$sdk_name_override"

[ -n "$remote_user" ] || { echo "remote user is empty in $remote_root" >&2; exit 2; }

if [ -n "$platform" ]; then
  case "$platform" in
    unisoc|mtk|rk) ;;
    *) echo "unsupported platform '$platform'; expected unisoc, mtk, or rk" >&2; exit 2 ;;
  esac
fi

ssh_host="${ssh_host:-$remote_user}"
local_platform=""
local_project=""
if [ -n "$platform" ]; then
  local_platform="${mount_root%/}/$platform"
fi
if [ -n "$platform" ] && [ -n "$sdk_name" ]; then
  local_project="$local_platform/$sdk_name"
fi

printf "REMOTE_ROOT=%q\n" "$remote_root"
printf "REMOTE_USER=%q\n" "$remote_user"
printf "SSH_HOST=%q\n" "$ssh_host"
printf "PLATFORM=%q\n" "$platform"
printf "SDK_NAME=%q\n" "$sdk_name"
printf "SAMBA_USER=%q\n" "$remote_user"
printf "LOCAL_PLATFORM=%q\n" "$local_platform"
printf "LOCAL_PROJECT=%q\n" "$local_project"
