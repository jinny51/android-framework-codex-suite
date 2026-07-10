#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

validate_manifest_skill_layout() {
  local failed=0
  local manifest plugin skill actual missing extra

  for manifest in "$repo_root"/manifests/*.toml; do
    plugin="$(basename "$manifest" .toml)"
    if [[ ! -d "$repo_root/plugins/$plugin/skills" ]]; then
      echo "plugin $plugin has manifest but no skills directory" >&2
      failed=1
      continue
    fi

    while IFS= read -r skill; do
      [[ -n "$skill" ]] || continue
      if [[ ! -f "$repo_root/plugins/$plugin/skills/$skill/SKILL.md" ]]; then
        echo "skill \`$skill\` is missing SKILL.md" >&2
        failed=1
      fi
    done < <(awk -F'"' '/^name = "/ {print $2}' "$manifest")

    while IFS= read -r actual; do
      [[ -n "$actual" ]] || continue
      if ! awk -F'"' '/^name = "/ {print $2}' "$manifest" | grep -Fxq "$actual"; then
        echo "skill \`$actual\` exists in $plugin but is not listed in manifests/$plugin.toml" >&2
        failed=1
      fi
    done < <(find "$repo_root/plugins/$plugin/skills" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
  done

  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_manifest_skill_layout

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-windows-*' | grep -q .; then
  echo "Windows-side skills must not be inside android-framework-ops" >&2
  exit 1
fi

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-macos-*' | grep -q .; then
  echo "macOS-native skills must not be inside android-framework-ops" >&2
  exit 1
fi

if find "$repo_root/plugins/android-framework-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'codex-chat-history-*' | grep -q .; then
  echo "codex chat history skills must not be inside android-framework-ops" >&2
  exit 1
fi

if find "$repo_root/plugins/android-wsl-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-wsl-*' | grep -q .; then
  echo "WSL platform skills should use current names such as android-source-access and android-remote-build-deploy" >&2
  exit 1
fi

if find "$repo_root/plugins/android-mac-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-macos-*' | grep -q .; then
  echo "macOS platform skills should use current android-mac-ops naming, not android-macos-* skill names" >&2
  exit 1
fi

if rg -n "android-wsl-source-access|android-wsl-remote-build-deploy|android-wsl-remote-channel|android-macos-source-access|android-macos-ops" "$repo_root/plugins" "$repo_root/docs" "$repo_root/manifests" >/tmp/akbs-plugin-old-skill-names.txt; then
  cat /tmp/akbs-plugin-old-skill-names.txt >&2
  echo "old platform skill/plugin names must not appear in current plugin sources" >&2
  exit 1
fi

if rg -n 'WSL source/build skills from android-framework-ops|通用源码接入、构建、推送和验收流程；这些属于 `android-framework-ops`' "$repo_root/plugins" "$repo_root/docs" >/tmp/akbs-plugin-layer-errors.txt; then
  cat /tmp/akbs-plugin-layer-errors.txt >&2
  echo "platform source/build responsibilities must stay in android-wsl-ops or android-mac-ops" >&2
  exit 1
fi

if rg -n "\.codex/android-macos-source-access-info" "$repo_root/plugins/android-mac-ops" "$repo_root/docs" >/tmp/akbs-plugin-old-mac-paths.txt; then
  cat /tmp/akbs-plugin-old-mac-paths.txt >&2
  echo "android-mac-ops must store registry and credential references under ~/.servers" >&2
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

validate_runtime_skill_cleanliness() {
  local failed=0
  local skill_dir rel top_level_name path

  while IFS= read -r -d '' skill_dir; do
    for top_level_name in README.md tests fixtures output reports pending submitted logs; do
      if [[ -e "$skill_dir/$top_level_name" ]]; then
        echo "runtime skill directory must not contain $top_level_name: $skill_dir/$top_level_name" >&2
        failed=1
      fi
    done

    while IFS= read -r -d '' path; do
      echo "runtime skill directory contains cache/build output: $path" >&2
      failed=1
    done < <(
      find "$skill_dir" \
        \( -path '*/__pycache__' -o -path '*/.pytest_cache' -o -name '*.pyc' -o -name '*.pyo' -o -name '*.log' -o -name '*.zip' -o -name '*.tar.gz' \) \
        -print0
    )

    while IFS= read -r -d '' path; do
      rel="${path#"$skill_dir"/}"
      case "$rel" in
        SKILL.md|references/*.md)
          ;;
        *)
          echo "runtime skill markdown must be SKILL.md or references/*.md: $path" >&2
          failed=1
          ;;
      esac
    done < <(find "$skill_dir" -type f -name '*.md' -print0)
  done < <(find "$repo_root/plugins" -path '*/skills/*/SKILL.md' -print0 | xargs -0 -n1 dirname -z)

  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_runtime_skill_cleanliness

echo "Skill layout validation passed"
