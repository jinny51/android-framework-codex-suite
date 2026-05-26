#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${1:-${CODEX_HOME:-$HOME/.codex}/team-skills}"

sync_skill() {
  local name="$1"
  local plugin="$2"
  local source_dir="$source_root/$name"
  local target_dir="$repo_root/plugins/$plugin/skills/$name"

  if [[ ! -f "$source_dir/SKILL.md" ]]; then
    echo "Missing source skill: $source_dir" >&2
    exit 1
  fi

  mkdir -p "$target_dir"
  rsync -a --delete \
    --exclude='config.toml' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='*.pem' \
    --exclude='*.key' \
    --exclude='*password*' \
    --exclude='*credential*' \
    "$source_dir/" "$target_dir/"
}

android_skills=(
  android-framework-change-workflow
  android-framework-patch-capture
  android-knowledge-search
  android-knowledge-intake
  android-remote-channel
  android-wsl-source-access
  android-wsl-remote-build-deploy
  android-windows-source-access
  android-windows-remote-build-deploy
)

workspace_care_skills=(
  codex-chat-history-cleaner
  codex-chat-history-context-extractor
)

for name in "${android_skills[@]}"; do
  sync_skill "$name" android-framework-ops
done

for name in "${workspace_care_skills[@]}"; do
  sync_skill "$name" codex-workspace-care
done

python3 "$repo_root/scripts/apply_plugin_overrides.py"

echo "Synced team skills from $source_root"
