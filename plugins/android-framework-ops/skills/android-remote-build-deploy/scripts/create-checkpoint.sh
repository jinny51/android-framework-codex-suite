#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh_host=""; project_root=""; project_id=""; name=""; purpose=""; preserve=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) ssh_host="${2:-}"; shift 2 ;;
    --remote-root|--project-root) project_root="${2:-}"; shift 2 ;;
    --project-id) project_id="${2:-}"; shift 2 ;;
    --name) name="${2:-}"; shift 2 ;;
    --purpose) purpose="${2:-}"; shift 2 ;;
    --preserve-legacy) preserve=true; shift ;;
    --ssh-user|--path|--output|--no-untracked|--dry-run)
      echo "ERROR: this legacy checkpoint option is not supported by remote-v2; use the formal entry" >&2
      exit 64
      ;;
    -h|--help)
      echo "create-checkpoint.sh --ssh-host HOST --project-root PATH --project-id ID --name ID [--purpose TEXT]"
      exit 0
      ;;
    *) echo "ERROR: unsupported legacy checkpoint argument: $1" >&2; exit 64 ;;
  esac
done
[[ -n "$ssh_host" && -n "$project_root" && -n "$project_id" && -n "$name" ]] || {
  echo "ERROR: remote-v2 checkpoint requires remote identity and --name" >&2
  exit 64
}
command=(python3 "$script_dir/remote-build-v2.py" --ssh-host "$ssh_host" --project-root "$project_root" --project-id "$project_id")
[[ "$preserve" == false ]] || command+=(--preserve-legacy)
command+=(checkpoint --name "$name" --purpose "$purpose")
exec "${command[@]}"
