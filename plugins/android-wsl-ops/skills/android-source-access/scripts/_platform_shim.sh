#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "$script_dir/../../.." && pwd)"
if ! plugin_name="$(
    python3 - "$plugin_root/.codex-plugin/plugin.json" <<'PY'
import json
import sys
from pathlib import Path

try:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    name = manifest["name"]
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(2)
if not isinstance(name, str) or not name:
    raise SystemExit(2)
print(name)
PY
)"; then
    echo "SOURCE_ACCESS_ENTRY_INVALID: platform manifest missing or invalid" >&2
    exit 2
fi
command_name="${1:?missing source-access command}"
shift

case "$plugin_name" in
  android-wsl-ops) expected_host="wsl" ;;
  android-mac-ops) expected_host="macos" ;;
  *)
    echo "SOURCE_ACCESS_ENTRY_INVALID: unsupported platform plugin $plugin_name" >&2
    exit 2
    ;;
esac

exec python3 "$script_dir/_core_source_access.py" \
  --expected-host "$expected_host" \
  --command "$command_name" \
  -- "$@"
