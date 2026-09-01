#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(cd "$script_dir/../../.." && pwd)"
plugin_name="$(basename "$plugin_root")"
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
