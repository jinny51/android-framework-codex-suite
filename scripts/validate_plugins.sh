#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py"

cleanup_caches() {
  find "$repo_root" -type d \( -name '.pytest_cache' -o -name '__pycache__' \) -prune -exec rm -rf {} +
  find "$repo_root" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
}

if [[ ! -f "$validator" ]]; then
  echo "Plugin validator not found: $validator" >&2
  exit 1
fi

cleanup_caches

for plugin in android-framework-ops jinny-android-practices android-wsl-ops android-mac-ops codex-workspace-care; do
  python3 "$validator" "$repo_root/plugins/$plugin"
done

"$repo_root/scripts/validate_skill_layout.sh"

cleanup_caches

echo "Plugin validation passed"
