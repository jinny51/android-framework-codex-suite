#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
ARTIFACT_GUARD=(python3 -m android_framework_ops.artifact_paths)
OWNER_TOKEN=""
DIAGNOSTICS_COMMITTED=0
MANAGED_OUTPUT=0
OUTPUT_HELPER=""
AKBS_AUTHORITY_ROOT=""
TASK_ID="android-framework-change-workflow"
RUN_ID=""

cleanup_diagnostics() {
  local status="${1:-1}"
  local cleanup_status=0
  trap - EXIT INT TERM HUP
  set +e
  if [[ "$DIAGNOSTICS_COMMITTED" == "0" && -n "$OWNER_TOKEN" ]]; then
    if [[ "$MANAGED_OUTPUT" == "1" ]]; then
      python3 "$OUTPUT_HELPER" --root "$AKBS_AUTHORITY_ROOT" owned-cleanup \
        --task-id "$TASK_ID" --run-id "$RUN_ID" --token "$OWNER_TOKEN" \
        --purpose "framework diagnostics output" >/dev/null
    else
      "${ARTIFACT_GUARD[@]}" --owned-cleanup --token "$OWNER_TOKEN" \
        --purpose "framework diagnostics output" "$OUT_DIR"
    fi
    cleanup_status=$?
  fi
  if [[ "$status" == "0" && "$cleanup_status" != "0" ]]; then
    status="$cleanup_status"
  fi
  exit "$status"
}

usage() {
  cat <<'EOF'
Usage: collect_diagnostics.sh [--out DIR] [--serial SERIAL] [--package PACKAGE]

Collect focused Android framework diagnostics with adb:
  - logcat snapshot
  - dumpsys activity/window/input/display/SurfaceFlinger/package
  - device_config list

EOF
}

OUT_DIR=""
SERIAL=""
PACKAGE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --serial|-s)
      SERIAL="${2:-}"
      shift 2
      ;;
    --package)
      PACKAGE="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v adb >/dev/null 2>&1; then
  echo "adb not found in PATH." >&2
  exit 2
fi

ADB=(adb)
if [[ -n "$SERIAL" ]]; then
  ADB=(adb -s "$SERIAL")
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$OUT_DIR" ]]; then
  AKBS_AUTHORITY_ROOT="${AKBS_ROOT:-$HOME/akbs}"
  OUTPUT_HELPER="${AKBS_OUTPUTS_HELPER:-$AKBS_AUTHORITY_ROOT/maintainer/scripts/akbs_outputs.py}"
  if [[ ! -f "$OUTPUT_HELPER" ]]; then
    echo "AKBS canonical outputs helper not found: $OUTPUT_HELPER; initialize AKBS or pass --out." >&2
    exit 2
  fi
  RUN_ID="$STAMP-$$"
  OWNED_JSON="$(python3 "$OUTPUT_HELPER" --root "$AKBS_AUTHORITY_ROOT" owned-create \
    --task-id "$TASK_ID" --run-id "$RUN_ID" --purpose "framework diagnostics output")"
  OUT_DIR="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$OWNED_JSON")"
  OWNER_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$OWNED_JSON")"
  MANAGED_OUTPUT=1
else
  OUT_DIR="$("${ARTIFACT_GUARD[@]}" --purpose "framework diagnostics output" "$OUT_DIR")"
  OWNER_TOKEN="$("${ARTIFACT_GUARD[@]}" --owned-create --purpose "framework diagnostics output" "$OUT_DIR")"
fi
trap 'cleanup_diagnostics "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

run_capture() {
  local name="$1"
  shift
  echo "capturing $name"
  if ! "${ADB[@]}" "$@" >"$OUT_DIR/$name.txt" 2>"$OUT_DIR/$name.err"; then
    echo "failed: $name" >>"$OUT_DIR/failures.txt"
  fi
}

run_capture "getprop" shell getprop
run_capture "logcat-dump" logcat -d -v threadtime
run_capture "dumpsys-activity-activities" shell dumpsys activity activities
run_capture "dumpsys-activity-displays" shell dumpsys activity displays
run_capture "dumpsys-window" shell dumpsys window
run_capture "dumpsys-input" shell dumpsys input
run_capture "dumpsys-display" shell dumpsys display
run_capture "dumpsys-surfaceflinger" shell dumpsys SurfaceFlinger
run_capture "device-config" shell device_config list

if [[ -n "$PACKAGE" ]]; then
  run_capture "dumpsys-package-$PACKAGE" shell dumpsys package "$PACKAGE"
fi

if [[ "$MANAGED_OUTPUT" == "1" ]]; then
  PROMOTED_JSON="$(python3 "$OUTPUT_HELPER" --root "$AKBS_AUTHORITY_ROOT" owned-promote \
    --task-id "$TASK_ID" --run-id "$RUN_ID" --token "$OWNER_TOKEN" \
    --purpose "framework diagnostics output" --category diagnostics \
    --item-id "android-framework-diagnostics-$RUN_ID")"
  OUT_DIR="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])' <<<"$PROMOTED_JSON")"
else
  "${ARTIFACT_GUARD[@]}" --owned-commit --token "$OWNER_TOKEN" \
    --purpose "framework diagnostics output" "$OUT_DIR"
fi
DIAGNOSTICS_COMMITTED=1
echo "diagnostics: $OUT_DIR"
