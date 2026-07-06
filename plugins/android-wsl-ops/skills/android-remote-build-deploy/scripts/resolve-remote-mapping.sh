#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
resolve-remote-mapping.sh --project /local/repo/path [options]

Resolve SSH_HOST and REMOTE_ROOT from android-source-access's local
mount registry.

Required:
  --project PATH        Local WSL project path.

Optional:
  --registry-dir PATH   Default: $HOME/.servers/projects.

Output:
  Shell-style KEY=VALUE lines when a remembered mapping exists.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

PROJECT_PATH=""
REGISTRY_DIR="$HOME/.servers/projects"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_PATH="${2:-}"; shift 2 ;;
    --registry-dir) REGISTRY_DIR="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$PROJECT_PATH" ]] || die "--project is required"
[[ "$PROJECT_PATH" == /* ]] || die "--project must be absolute"
[[ -d "$REGISTRY_DIR" ]] || die "registry dir not found: $REGISTRY_DIR"

shopt -s nullglob
for file in "$REGISTRY_DIR"/*.env; do
  PROJECT_PATHS=()
  REMOTE_SSH_HOSTS=()
  REMOTE_ROOTS=()
  PLATFORMS=()
  SDK_NAMES=()
  # shellcheck disable=SC1090
  source "$file"
  for i in "${!PROJECT_PATHS[@]}"; do
    if [[ "${PROJECT_PATHS[$i]}" == "$PROJECT_PATH" ]]; then
      ssh_host="${REMOTE_SSH_HOSTS[$i]:-}"
      remote_root="${REMOTE_ROOTS[$i]:-}"
      platform="${PLATFORMS[$i]:-}"
      sdk_name="${SDK_NAMES[$i]:-}"
      [[ -n "$ssh_host" ]] || die "remembered project has no SSH host: $PROJECT_PATH"
      [[ -n "$remote_root" ]] || die "remembered project has no remote root: $PROJECT_PATH"
      printf "SSH_HOST=%q\n" "$ssh_host"
      printf "REMOTE_ROOT=%q\n" "$remote_root"
      [[ -n "$platform" ]] && printf "PLATFORM=%q\n" "$platform"
      [[ -n "$sdk_name" ]] && printf "SDK_NAME=%q\n" "$sdk_name"
      printf "MAPPING_REGISTRY=%q\n" "$file"
      exit 0
    fi
  done
done

die "no remembered remote mapping for project: $PROJECT_PATH"
