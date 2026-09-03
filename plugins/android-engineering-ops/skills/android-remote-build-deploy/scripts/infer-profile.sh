#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ssh_host=""; project_root=""; project_id=""; working_subpath="."; profile=""; output=""
paths=(); preserve=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) ssh_host="${2:-}"; shift 2 ;;
    --remote-root|--project-root) project_root="${2:-}"; shift 2 ;;
    --project-id) project_id="${2:-}"; shift 2 ;;
    --working-subpath) working_subpath="${2:-}"; shift 2 ;;
    --path) paths+=("${2:-}"); shift 2 ;;
    --profile) profile="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    --preserve-legacy) preserve=true; shift ;;
    --repo|--from-file)
      echo "ERROR: local/mounted profile inference was removed; provide remote identity and --path" >&2
      exit 64
      ;;
    -h|--help)
      echo "infer-profile.sh --ssh-host HOST --project-root PATH --project-id ID --path REL [--working-subpath REL]"
      exit 0
      ;;
    *) echo "ERROR: unsupported legacy inference argument: $1" >&2; exit 64 ;;
  esac
done
[[ -n "$ssh_host" && -n "$project_root" && -n "$project_id" && ${#paths[@]} -gt 0 ]] || {
  echo "ERROR: remote-v2 inference requires remote identity and at least one --path" >&2
  exit 64
}
command=(python3 "$script_dir/remote-build-v2.py" --ssh-host "$ssh_host" --project-root "$project_root" \
  --project-id "$project_id" --working-subpath "$working_subpath")
[[ "$preserve" == false ]] || command+=(--preserve-legacy)
command+=(infer-profile)
for path in "${paths[@]}"; do command+=(--path "$path"); done
[[ -z "$profile" ]] || command+=(--profile "$profile")
[[ -z "$output" ]] || command+=(--output "$output")
exec "${command[@]}"
