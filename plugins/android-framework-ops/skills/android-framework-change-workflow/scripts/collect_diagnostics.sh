#!/usr/bin/env bash
set -euo pipefail

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
  OUT_DIR="android-fw-diagnostics-$STAMP"
fi
mkdir -p "$OUT_DIR"

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

echo "diagnostics: $OUT_DIR"
