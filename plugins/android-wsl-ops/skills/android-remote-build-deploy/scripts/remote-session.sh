#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

candidate_paths=(
  "${CODEX_HOME:-$HOME/.codex}/skills/android-remote-channel/scripts/remote-channel.sh"
  "$SCRIPT_DIR/../../android-remote-channel/scripts/remote-channel.sh"
)

for candidate in "${candidate_paths[@]}"; do
  if [[ -x "$candidate" ]]; then
    exec "$candidate" "$@"
  fi
done

echo "ERROR: android-remote-channel is not installed or not found." >&2
echo "Expected one of:" >&2
printf '  %s\n' "${candidate_paths[@]}" >&2
exit 127
