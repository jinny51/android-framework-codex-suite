#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh_host=""; project_root=""; project_id=""; preserve=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) ssh_host="${2:-}"; shift 2 ;;
    --remote-root|--project-root) project_root="${2:-}"; shift 2 ;;
    --project-id) project_id="${2:-}"; shift 2 ;;
    --preserve-legacy) preserve=true; shift ;;
    --repo)
      echo "ERROR: --repo mounted-source generation was removed; use --project-root and remote-v2" >&2
      exit 64
      ;;
    --force) shift ;; # Content-addressed v2 installation is already idempotent.
    -h|--help)
      echo "ensure-build-session.sh --ssh-host HOST --project-root PATH --project-id ID [--preserve-legacy]"
      exit 0
      ;;
    *) echo "ERROR: unsupported legacy ensure argument: $1" >&2; exit 64 ;;
  esac
done
[[ -n "$ssh_host" && -n "$project_root" && -n "$project_id" ]] || {
  echo "ERROR: remote-v2 install requires --ssh-host, --project-root, and --project-id" >&2
  exit 64
}
command=(python3 "$script_dir/remote-build-v2.py" --ssh-host "$ssh_host" --project-root "$project_root" --project-id "$project_id")
[[ "$preserve" == false ]] || command+=(--preserve-legacy)
command+=(install)
exec "${command[@]}"
