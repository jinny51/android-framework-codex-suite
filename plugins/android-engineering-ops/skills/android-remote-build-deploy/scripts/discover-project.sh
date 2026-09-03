#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh_host=""; project_root=""; project_id=""; working_subpath="."; output=""
extra=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) ssh_host="${2:-}"; shift 2 ;;
    --remote-root|--project-root) project_root="${2:-}"; shift 2 ;;
    --project-id) project_id="${2:-}"; shift 2 ;;
    --working-subpath) working_subpath="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --preserve-legacy) extra+=(--preserve-legacy); shift ;;
    --ignore-repo-config) shift ;; # The v2 runtime never trusts legacy config implicitly.
    -h|--help)
      echo "discover-project.sh --ssh-host HOST --project-root PATH --project-id ID [--working-subpath REL] [--output FILE]"
      exit 0
      ;;
    *) echo "ERROR: unsupported legacy discovery argument: $1" >&2; exit 64 ;;
  esac
done
[[ -n "$ssh_host" && -n "$project_root" && -n "$project_id" ]] || {
  echo "ERROR: remote-v2 discovery requires --ssh-host, --project-root, and --project-id" >&2
  exit 64
}
command=(python3 "$script_dir/remote-build-v2.py" --ssh-host "$ssh_host" --project-root "$project_root" \
  --project-id "$project_id" --working-subpath "$working_subpath" "${extra[@]}" discover)
[[ -z "$output" ]] || command+=(--output "$output")
exec "${command[@]}"
