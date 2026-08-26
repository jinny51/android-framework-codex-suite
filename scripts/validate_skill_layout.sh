#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/validator_cleanup.sh"
validator_cleanup_install "$repo_root"

repo_search() {
  local pattern="$1"
  shift
  if command -v rg >/dev/null 2>&1; then
    rg -n "$pattern" "$@"
    return
  fi
  python3 - "$pattern" "$@" <<'PY'
import re
import sys
from pathlib import Path

pattern = re.compile(sys.argv[1])
found = False
for raw_root in sys.argv[2:]:
    root = Path(raw_root)
    paths = [root] if root.is_file() else root.rglob("*")
    for path in paths:
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                print(f"{path}:{number}:{line}")
                found = True
raise SystemExit(0 if found else 1)
PY
}

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
    done < <(find "$repo_root/plugins/$plugin/skills" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
  done

  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_manifest_skill_layout

failed=0
while IFS= read -r script; do
  IFS= read -r first_line < "$script" || true
  if [[ "$first_line" == '#!'* && ! -x "$script" ]]; then
    echo "runtime script with a shebang must be executable: $script" >&2
    failed=1
  fi
done < <(find "$repo_root/plugins" -path '*/skills/*/scripts/*' -type f | sort)
if [[ "$failed" != "0" ]]; then
  exit 1
fi

core_manifest_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$repo_root/plugins/android-framework-ops/.codex-plugin/plugin.json")"
core_rules_version="$(sed -n 's/^ANDROID_FRAMEWORK_OPS_PLUGIN_VERSION = "\([^"]*\)"/\1/p' "$repo_root/plugins/android-framework-ops/lib/android_framework_ops/knowledge_rules.py")"
if [[ -z "$core_rules_version" || "$core_manifest_version" != "$core_rules_version" ]]; then
  echo "android-framework-ops manifest/rules version mismatch: manifest=$core_manifest_version rules=${core_rules_version:-missing}" >&2
  exit 1
fi

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
  echo "WSL platform skills should use current platform-neutral names such as android-source-access" >&2
  exit 1
fi

if find "$repo_root/plugins/android-mac-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-macos-*' | grep -q .; then
  echo "macOS platform skills should use current android-mac-ops naming, not android-macos-* skill names" >&2
  exit 1
fi

old_skill_names="$VALIDATOR_CLEANUP_TMPDIR/old-skill-names.txt"
if repo_search "android-wsl-source-access|android-wsl-remote-build-deploy|android-wsl-remote-channel|android-macos-source-access|android-macos-ops" "$repo_root/plugins" "$repo_root/docs" "$repo_root/manifests" >"$old_skill_names"; then
  cat "$old_skill_names" >&2
  echo "old platform skill/plugin names must not appear in current plugin sources" >&2
  exit 1
fi

if find "$repo_root/plugins/android-wsl-ops/skills" "$repo_root/plugins/android-mac-ops/skills" -mindepth 1 -maxdepth 1 -type d -name 'android-remote-build-deploy' | grep -q .; then
  echo "android-remote-build-deploy must have one platform-neutral implementation in android-framework-ops" >&2
  exit 1
fi

layer_errors="$VALIDATOR_CLEANUP_TMPDIR/layer-errors.txt"
if repo_search 'WSL source/build skills from android-framework-ops|通用源码接入、构建、推送和验收流程；这些属于 `android-framework-ops`' "$repo_root/plugins" "$repo_root/docs" >"$layer_errors"; then
  cat "$layer_errors" >&2
  echo "platform source access stays in android-wsl-ops or android-mac-ops; shared build/deploy stays in android-framework-ops" >&2
  exit 1
fi

old_mac_paths="$VALIDATOR_CLEANUP_TMPDIR/old-mac-paths.txt"
if repo_search "\.codex/android-macos-source-access-info" "$repo_root/plugins/android-mac-ops" "$repo_root/docs" >"$old_mac_paths"; then
  cat "$old_mac_paths" >&2
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
  local skill_file skill_dir rel top_level_name path

  while IFS= read -r -d '' skill_file; do
    skill_dir="${skill_file%/SKILL.md}"
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
  done < <(find "$repo_root/plugins" -path '*/skills/*/SKILL.md' -print0)

  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_runtime_skill_cleanliness

validate_guarded_output_entrypoints() {
  local failed=0
  local entry file marker
  local -a entries=(
    "plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_framework_patch.py|require_safe_artifact_path"
    "plugins/android-framework-ops/skills/android-framework-change-workflow/scripts/collect_diagnostics.sh|--owned-create"
    "plugins/android-framework-ops/skills/android-framework-change-workflow/scripts/extract_video_frames.py|require_safe_artifact_path"
    "plugins/android-framework-ops/skills/android-remote-build-deploy/scripts/push_artifacts.py|require_safe_artifact_path"
    "plugins/android-framework-ops/skills/android-remote-build-deploy/scripts/remote-build-v2.py|require_safe_artifact_path"
    "plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_remote_snapshot.py|require_safe_artifact_path"
    "plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/scripts/extract_codex_context.py|require_safe_artifact_path"
  )
  for entry in "${entries[@]}"; do
    file="${entry%%|*}"
    marker="${entry#*|}"
    if ! grep -Fq -- "$marker" "$repo_root/$file"; then
      echo "explicit output entrypoint does not call the path guard: $file" >&2
      failed=1
    fi
  done
  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
}

validate_guarded_output_entrypoints

echo "Skill layout validation passed"
