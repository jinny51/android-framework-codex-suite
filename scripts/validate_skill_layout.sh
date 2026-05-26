#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

count_skills() {
  local plugin="$1"
  find "$repo_root/plugins/$plugin/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l
}

android_count="$(count_skills android-framework-ops | tr -d ' ')"
workspace_count="$(count_skills codex-workspace-care | tr -d ' ')"

if [[ "$android_count" != "9" ]]; then
  echo "android-framework-ops should contain 9 skills, found $android_count" >&2
  exit 1
fi

if [[ "$workspace_count" != "2" ]]; then
  echo "codex-workspace-care should contain 2 skills, found $workspace_count" >&2
  exit 1
fi

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'codex-chat-history-*' | grep -q .; then
  echo "codex chat history skills must not be inside android-framework-ops" >&2
  exit 1
fi

echo "Skill layout validation passed"
