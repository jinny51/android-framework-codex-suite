#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py"
source "$repo_root/scripts/validator_cleanup.sh"
validator_cleanup_install "$repo_root"

if [[ ! -f "$validator" ]]; then
  echo "Plugin validator not found: $validator" >&2
  exit 1
fi

for plugin in android-framework-ops jinny-android-practices android-wsl-ops android-mac-ops codex-workspace-care; do
  python3 "$validator" "$repo_root/plugins/$plugin"
done

"$repo_root/scripts/validate_skill_layout.sh"

python3 -m pytest --capture=no "$repo_root/tests"

python3 "$repo_root/plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/scripts/self_test_extract_codex_context.py"
python3 "$repo_root/scripts/test_validator_cleanup.py"

system_root="${AKBS_SYSTEM_ROOT:-${AKBS_ROOT:-$HOME/akbs}/linux/system}"
if [[ "$(uname -s)" == "Linux" && -f "$system_root/akbs_active/app.py" ]]; then
  python3 "$repo_root/scripts/validate_incoming_contract_gate.py" --system-root "$system_root"
fi

echo "Plugin validation passed"
