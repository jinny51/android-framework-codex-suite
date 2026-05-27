#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

count_skills() {
  local plugin="$1"
  find "$repo_root/plugins/$plugin/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l
}

android_count="$(count_skills android-framework-ops | tr -d ' ')"
windows_count="$(count_skills android-framework-windows-ops | tr -d ' ')"
workspace_count="$(count_skills codex-workspace-care | tr -d ' ')"

if [[ "$android_count" != "7" ]]; then
  echo "android-framework-ops should contain 7 skills, found $android_count" >&2
  exit 1
fi

if [[ "$windows_count" != "3" ]]; then
  echo "android-framework-windows-ops should contain 3 skills, found $windows_count" >&2
  exit 1
fi

if [[ "$workspace_count" != "2" ]]; then
  echo "codex-workspace-care should contain 2 skills, found $workspace_count" >&2
  exit 1
fi

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-windows-*' | grep -q .; then
  echo "Windows-native skills must not be inside android-framework-ops" >&2
  exit 1
fi

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'codex-chat-history-*' | grep -q .; then
  echo "codex chat history skills must not be inside android-framework-ops" >&2
  exit 1
fi

validate_skill_metadata() {
  local failed=0
  local skill_file skill_dir skill_name agent_file

  while IFS= read -r -d '' skill_file; do
    skill_dir="${skill_file%/SKILL.md}"
    skill_name="$(basename "$skill_dir")"
    agent_file="$skill_dir/agents/openai.yaml"

    if [[ ! -f "$agent_file" ]]; then
      echo "$skill_name is missing agents/openai.yaml" >&2
      failed=1
      continue
    fi

    if ! grep -Fq "\$$skill_name" "$agent_file"; then
      echo "$agent_file default_prompt should reference \$$skill_name" >&2
      failed=1
    fi
  done < <(find "$repo_root/plugins" -path '*/skills/*/SKILL.md' -print0)

  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_skill_metadata

echo "Skill layout validation passed"
